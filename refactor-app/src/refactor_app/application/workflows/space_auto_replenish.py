from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import floor
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import (
    BackfillSessionWorkflow,
    ensure_account_proxy_url,
)
from refactor_app.application.workflows.downstream_provider import provider_from_channel
from refactor_app.application.workflows.protocol_registration import (
    EMAIL_PROTOCOL_NO_PHONE,
    ProtocolRegistrationInput,
    ProtocolRegistrationWorkflow,
)
from refactor_app.application.workflows.proxy import (
    ensure_team_admin_static_proxy_url_in_session,
)
from refactor_app.application.workflows.space_authorization import (
    CreateBusinessAccessTokenCredentialInput,
    CreateBusinessAccessTokenCredentialWorkflow,
    run_business_access_token_rate_limited,
)
from refactor_app.application.workflows.space_direct_push import (
    SpaceDirectPushInput,
    SpaceDirectPushWorkflow,
    SpaceDirectPushWorkflowError,
)
from refactor_app.application.workflows.space_recycle import (
    SpaceRecycleSweepWorkflow,
    manually_settle_pushed_binding_from_usage_state,
)
from refactor_app.infrastructure.db.models import (
    DownstreamChannelModel,
    SpaceCredentialModel,
    SpaceCredentialUsageStateModel,
    SpaceMembershipModel,
    SpaceModel,
    SpacePushBindingModel,
    SpaceReplenishEmailModel,
    TeamAdminSessionModel,
    UserAccountModel,
)
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.contracts import OpenAIChatGPTProvider
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin

MAX_INVITE_BATCH_SIZE = 1000
INVITE_CONFIRM_DELAY_SECONDS = 120
REPLACEMENT_USAGE_PERCENT = 90


def _has_remote_seat_capacity(
    *,
    remote_user_count: int,
    seat_limit: int,
    replacing: bool,
) -> bool:
    effective_limit = floor(seat_limit * 1.5) if replacing else seat_limit
    return remote_user_count < effective_limit


def _team_admin_cookie_header(admin: TeamAdminSessionModel) -> str:
    cookie_header = str(admin.cookie_header or "").strip()
    session_token = str(admin.session_token or "").strip()
    cookie_name = "__Secure-next-auth.session-token"
    if not session_token or f"{cookie_name}=" in cookie_header:
        return cookie_header
    session_cookie = f"{cookie_name}={session_token}"
    return f"{session_cookie}; {cookie_header}" if cookie_header else session_cookie


def _replenishment_registration(
    *,
    space: SpaceModel,
    admin: TeamAdminSessionModel,
    admin_proxy_url: str,
) -> dict[str, Any]:
    seat_limit = int(space.seat_limit or 0)
    if not 1 <= seat_limit <= MAX_INVITE_BATCH_SIZE:
        raise SpaceAutoReplenishError(
            "business space seat limit must be between "
            f"1 and {MAX_INVITE_BATCH_SIZE}: {seat_limit}"
        )
    return {
        "admin_key": (admin.admin_email or admin.id).strip().casefold(),
        "admin_email": admin.admin_email,
        "name": space.name,
        "enabled": True,
        "credential_type": space.credential_type,
        "seat_limit": seat_limit,
        "admin_proxy_url": str(admin_proxy_url or "").strip(),
    }


class SpaceAutoReplenishError(RuntimeError):
    pass


@dataclass(frozen=True)
class _AdminContext:
    space_id: str
    external_space_id: str
    access_token: str
    cookie_header: str
    proxy_url: str


class InviteExecutorClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        request_timeout_s: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base_url = str(base_url or "").strip().rstrip("/")
        self._api_key = str(api_key or "").strip()
        if not self._base_url:
            raise SpaceAutoReplenishError("INVITE_EXECUTOR_BASE_URL is not configured")
        if not self._api_key:
            raise SpaceAutoReplenishError("INVITE_EXECUTOR_API_KEY is not configured")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(request_timeout_s),
            trust_env=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> InviteExecutorClient:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def create_batch(
        self,
        *,
        external_space_id: str,
        access_token: str,
        cookie_header: str,
        emails: Sequence[str],
        replenishment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not 1 <= len(emails) <= MAX_INVITE_BATCH_SIZE:
            raise SpaceAutoReplenishError(
                f"invite email count must be between 1 and {MAX_INVITE_BATCH_SIZE}"
            )
        try:
            response = self._client.post(
                f"{self._base_url}/v1/invite-batches",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "external_space_id": external_space_id,
                    "access_token": access_token,
                    "cookie_header": cookie_header,
                    "emails": list(emails),
                    **({"replenishment": replenishment} if replenishment else {}),
                },
            )
        except httpx.HTTPError as exc:
            raise SpaceAutoReplenishError(
                f"invite executor request failed: {type(exc).__name__}: {exc}"
            ) from exc
        if response.is_error:
            raise SpaceAutoReplenishError(
                f"invite executor returned HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SpaceAutoReplenishError("invite executor response is not JSON") from exc
        if not isinstance(payload, dict) or not str(payload.get("batch_id") or "").strip():
            raise SpaceAutoReplenishError("invite executor response missing batch_id")
        return payload

    def upsert_replenishment_space(
        self,
        *,
        external_space_id: str,
        registration: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = self._client.put(
                f"{self._base_url}/v1/replenishment/spaces/{external_space_id}",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=registration,
            )
        except httpx.HTTPError as exc:
            raise SpaceAutoReplenishError(
                f"invite executor hosting request failed: {type(exc).__name__}: {exc}"
            ) from exc
        if response.is_error:
            raise SpaceAutoReplenishError(
                "invite executor hosting returned "
                f"HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SpaceAutoReplenishError(
                "invite executor hosting response is not JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise SpaceAutoReplenishError(
                "invite executor hosting response has invalid structure"
            )
        return payload

    def delete_replenishment_space(self, *, external_space_id: str) -> dict[str, Any]:
        try:
            response = self._client.delete(
                f"{self._base_url}/v1/replenishment/spaces/{external_space_id}",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            raise SpaceAutoReplenishError(
                f"invite executor unhosting request failed: {type(exc).__name__}: {exc}"
            ) from exc
        if response.status_code == 404:
            return {"removed": False, "external_space_id": external_space_id}
        if response.is_error:
            raise SpaceAutoReplenishError(
                "invite executor unhosting returned "
                f"HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SpaceAutoReplenishError(
                "invite executor unhosting response is not JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise SpaceAutoReplenishError(
                "invite executor unhosting response has invalid structure"
            )
        return payload


def host_space_auto_replenishment(
    *,
    session_factory: Callable[[], Session],
    invite_executor_base_url: str,
    invite_executor_api_key: str,
    space_id: str,
) -> dict[str, Any]:
    with session_factory() as session:
        space = _active_business_space(session=session, space_id=space_id, lock=True)
        admin = _admin_session(session=session, space=space)
        if admin is None or not admin.access_token:
            raise SpaceAutoReplenishError("team admin session missing access token")
        admin_proxy_url = ensure_team_admin_static_proxy_url_in_session(
            session=session,
            team_admin_session_id=admin.id,
            bind_reason="space_auto_replenish_hosting",
        )
        external_space_id = space.external_space_id
        registration = {
            **_replenishment_registration(
                space=space,
                admin=admin,
                admin_proxy_url=admin_proxy_url,
            ),
            "admin_access_token": admin.access_token,
            "admin_cookie_header": _team_admin_cookie_header(admin),
        }
        session.commit()

    with InviteExecutorClient(
        base_url=invite_executor_base_url,
        api_key=invite_executor_api_key,
    ) as client:
        remote = client.upsert_replenishment_space(
            external_space_id=external_space_id,
            registration=registration,
        )

    with session_factory() as session:
        space = session.get(SpaceModel, space_id, with_for_update=True)
        if space is None:
            raise SpaceAutoReplenishError("space disappeared after remote hosting")
        space.auto_replenish_enabled = True
        space.updated_at = datetime.now(UTC)
        session.commit()
    return {
        "space_id": space_id,
        "external_space_id": external_space_id,
        "hosted": True,
        "remote": remote,
    }


def cancel_space_auto_replenishment_hosting(
    *,
    session_factory: Callable[[], Session],
    invite_executor_base_url: str,
    invite_executor_api_key: str,
    space_id: str,
) -> dict[str, Any]:
    with session_factory() as session:
        space = session.get(SpaceModel, str(space_id or "").strip())
        if space is None:
            raise SpaceAutoReplenishError("space not found")
        if space.space_type != "business" or not space.external_space_id:
            raise SpaceAutoReplenishError("hosting only supports business spaces")
        external_space_id = space.external_space_id

    with InviteExecutorClient(
        base_url=invite_executor_base_url,
        api_key=invite_executor_api_key,
    ) as client:
        remote = client.delete_replenishment_space(
            external_space_id=external_space_id,
        )

    with session_factory() as session:
        space = session.get(SpaceModel, space_id, with_for_update=True)
        if space is None:
            raise SpaceAutoReplenishError("space disappeared after remote unhosting")
        space.auto_replenish_enabled = False
        space.updated_at = datetime.now(UTC)
        session.commit()
    return {
        "space_id": space_id,
        "external_space_id": external_space_id,
        "hosted": False,
        "remote_removed": bool(remote.get("removed")),
    }


class SpaceAutoReplenishWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin,
        openai_provider: OpenAIChatGPTProvider,
        invite_executor_base_url: str,
        invite_executor_api_key: str,
        registration_proxy_country: str = "US",
        totp_code_resolver: Callable[[str], str] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider
        self._openai_provider = openai_provider
        self._invite_executor_base_url = invite_executor_base_url
        self._invite_executor_api_key = invite_executor_api_key
        self._registration_proxy_country = registration_proxy_country
        self._totp_code_resolver = totp_code_resolver

    def import_emails(self, emails: Sequence[str]) -> dict[str, int]:
        return import_space_replenish_emails(
            session_factory=self._session_factory,
            emails=emails,
        )

    def prepare_invites(
        self,
        *,
        space_id: str,
        invite_count: int = MAX_INVITE_BATCH_SIZE,
        run_id: str = "",
    ) -> dict[str, Any]:
        requested_count = int(invite_count or MAX_INVITE_BATCH_SIZE)
        if requested_count != MAX_INVITE_BATCH_SIZE:
            raise SpaceAutoReplenishError(
                f"automatic replenish invite count must be exactly {MAX_INVITE_BATCH_SIZE}"
            )
        reserved_ids: list[str] = []
        emails: list[str] = []
        with self._session_factory() as session:
            space = _active_business_space(session=session, space_id=space_id, lock=True)
            pending_count = int(
                session.scalar(
                    select(func.count())
                    .select_from(SpaceReplenishEmailModel)
                    .where(
                        SpaceReplenishEmailModel.space_id == space.id,
                        SpaceReplenishEmailModel.invite_status.in_(("reserved", "confirm_pending")),
                    )
                )
                or 0
            )
            if pending_count:
                return {
                    "status": "skipped",
                    "reason": "space_has_pending_invite_confirmation",
                    "pending_count": pending_count,
                    "selected_count": 0,
                }

            selected = self._select_invite_candidates(
                session=session,
                limit=requested_count,
            )
            if len(selected) != requested_count:
                raise SpaceAutoReplenishError(
                    "not enough local replenish email candidates: "
                    f"required={requested_count},available={len(selected)}"
                )
            now = datetime.now(UTC)
            for row in selected:
                row.space_id = space.id
                row.invite_status = "reserved"
                row.process_status = "idle"
                row.invite_batch_id = ""
                row.invite_confirm_after = None
                row.invite_confirmed_at = None
                row.failure_code = ""
                row.failure_message = ""
                row.updated_at = now
                reserved_ids.append(row.id)
                emails.append(row.email)
            external_space_id = space.external_space_id
            admin = _admin_session(session=session, space=space)
            if admin is None or not admin.access_token:
                raise SpaceAutoReplenishError("team admin session missing access token")
            admin_proxy_url = ensure_team_admin_static_proxy_url_in_session(
                session=session,
                team_admin_session_id=admin.id,
                bind_reason="space_auto_replenish_hosting",
            )
            admin_access_token = admin.access_token
            admin_cookie_header = _team_admin_cookie_header(admin)
            replenishment_registration = _replenishment_registration(
                space=space,
                admin=admin,
                admin_proxy_url=admin_proxy_url,
            )
            session.commit()

        try:
            with InviteExecutorClient(
                base_url=self._invite_executor_base_url,
                api_key=self._invite_executor_api_key,
            ) as client:
                batch = client.create_batch(
                    external_space_id=external_space_id,
                    access_token=admin_access_token,
                    cookie_header=admin_cookie_header,
                    emails=emails,
                    replenishment=replenishment_registration,
                )
        except Exception as exc:
            self._release_reserved_invites(reserved_ids=reserved_ids, error=exc)
            raise

        batch_id = str(batch["batch_id"])
        now = datetime.now(UTC)
        with self._session_factory() as session:
            rows = session.scalars(
                select(SpaceReplenishEmailModel).where(
                    SpaceReplenishEmailModel.id.in_(reserved_ids)
                )
            ).all()
            for row in rows:
                row.invite_batch_id = batch_id
                row.invite_status = "confirm_pending"
                row.invite_confirm_after = now + timedelta(seconds=INVITE_CONFIRM_DELAY_SECONDS)
                row.updated_at = now
            session.commit()
        self._event(
            run_id=run_id,
            event_type="space_auto_replenish.invites_submitted",
            message="1000 replenish invitation emails submitted to invite executor",
            data_json={
                "space_id": space_id,
                "batch_id": batch_id,
                "selected_count": len(emails),
            },
        )
        return {
            "status": "submitted",
            "space_id": space_id,
            "batch_id": batch_id,
            "selected_count": len(emails),
            "confirm_after": (now + timedelta(seconds=INVITE_CONFIRM_DELAY_SECONDS)).isoformat(),
        }

    def reconcile_pending_invites(
        self,
        *,
        space_id: str,
        run_id: str = "",
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            due_ids = list(
                session.scalars(
                    select(SpaceReplenishEmailModel.id).where(
                        SpaceReplenishEmailModel.space_id == space_id,
                        SpaceReplenishEmailModel.invite_status == "confirm_pending",
                        SpaceReplenishEmailModel.invite_confirm_after.is_not(None),
                        SpaceReplenishEmailModel.invite_confirm_after <= now,
                    )
                ).all()
            )
        if not due_ids:
            return {"checked": 0, "confirmed": 0, "failed": 0}

        context = self._admin_context(
            space_id=space_id,
            bind_reason="space_auto_replenish_invite_confirm",
        )
        try:
            remote_invites = self._openai_provider.list_account_invites(
                access_token=context.access_token,
                account_id=context.external_space_id,
                cookie_header=context.cookie_header,
                page_size=100,
                proxy_url=context.proxy_url,
            )
        except Exception as exc:
            self._event(
                run_id=run_id,
                event_type="space_auto_replenish.invite_confirm_failed",
                message="remote pending invitations query failed; local state retained",
                level="ERROR",
                data_json={"space_id": space_id, "error": f"{type(exc).__name__}: {exc}"},
            )
            raise
        remote_email_keys = {
            email.casefold()
            for email in (_remote_invite_email(item) for item in remote_invites)
            if email
        }
        confirmed = 0
        failed = 0
        with self._session_factory() as session:
            rows = session.scalars(
                select(SpaceReplenishEmailModel).where(
                    SpaceReplenishEmailModel.id.in_(due_ids),
                    SpaceReplenishEmailModel.invite_status == "confirm_pending",
                )
            ).all()
            for row in rows:
                if row.email_key in remote_email_keys:
                    row.invite_status = "confirmed"
                    row.invite_confirmed_at = now
                    row.failure_code = ""
                    row.failure_message = ""
                    confirmed += 1
                else:
                    row.invite_status = "failed"
                    row.process_status = "failed"
                    row.failure_code = "remote_pending_invite_missing"
                    row.failure_message = (
                        "email was not present in the remote pending invitation list"
                    )
                    failed += 1
                row.updated_at = now
            session.commit()
        self._event(
            run_id=run_id,
            event_type="space_auto_replenish.invites_confirmed",
            message="remote pending invitations reconciled",
            data_json={
                "space_id": space_id,
                "checked": len(due_ids),
                "confirmed": confirmed,
                "failed": failed,
            },
        )
        return {"checked": len(due_ids), "confirmed": confirmed, "failed": failed}

    def run_space_cycle(self, *, space_id: str, run_id: str = "", work_id: str = "") -> dict:
        with self._session_factory() as session:
            space = _active_business_space(session=session, space_id=space_id)
            if not space.auto_replenish_enabled:
                return {"status": "skipped", "reason": "auto_replenish_disabled"}

        invite_result: dict[str, Any]
        try:
            invite_result = self.reconcile_pending_invites(space_id=space_id, run_id=run_id)
        except Exception as exc:
            return {
                "status": "waiting",
                "reason": "remote_invite_confirmation_failed",
                "error": f"{type(exc).__name__}: {exc}",
            }

        remove_row_id = self._pending_removal_row_id(space_id=space_id)
        if remove_row_id:
            result = self._remove_replaced_member(row_id=remove_row_id, run_id=run_id)
            return {**result, "invite_reconcile": invite_result}

        self._refresh_pushed_usage(space_id=space_id, run_id=run_id)
        removal_result = self._complete_and_remove_replacement(
            space_id=space_id,
            run_id=run_id,
        )
        if removal_result is not None:
            result = removal_result
            return {**result, "invite_reconcile": invite_result}

        unpushed_credential_id = self._active_unpushed_credential_id(space_id=space_id)
        if unpushed_credential_id:
            push_result = self._push_credential(unpushed_credential_id)
            removal_result = self._complete_and_remove_replacement(
                space_id=space_id,
                run_id=run_id,
            )
            if removal_result is not None:
                return {
                    **removal_result,
                    "space_credential_id": unpushed_credential_id,
                    "push": push_result,
                    "invite_reconcile": invite_result,
                }
            return {
                "status": "push_pending_credential",
                "space_credential_id": unpushed_credential_id,
                "push": push_result,
                "invite_reconcile": invite_result,
            }

        provisioning_row_id = self._provisioning_row_id(space_id=space_id)
        if provisioning_row_id:
            return {
                "status": "waiting",
                "reason": "space_has_provisioning_candidate",
                "space_replenish_email_id": provisioning_row_id,
                "invite_reconcile": invite_result,
            }

        context = self._admin_context(
            space_id=space_id,
            bind_reason="space_auto_replenish_member_count",
        )
        try:
            remote_members = self._openai_provider.list_account_users(
                access_token=context.access_token,
                account_id=context.external_space_id,
                cookie_header=context.cookie_header,
                page_size=100,
                proxy_url=context.proxy_url,
            )
        except Exception as exc:
            return {
                "status": "waiting",
                "reason": "remote_users_query_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "invite_reconcile": invite_result,
            }
        remote_user_count = len(remote_members)
        remote_member_count = max(0, remote_user_count - 1)
        with self._session_factory() as session:
            space = _active_business_space(session=session, space_id=space_id)
            seat_limit = int(space.seat_limit or 0)
            if seat_limit <= 0:
                return {
                    "status": "waiting",
                    "reason": "seat_limit_not_configured",
                    "remote_user_count": remote_user_count,
                    "remote_member_count": remote_member_count,
                    "invite_reconcile": invite_result,
                }
            replacement_credential_id = _replacement_required_credential_id(
                session=session,
                space=space,
            )
            replacement_cap = floor(seat_limit * 1.5)
            if replacement_credential_id:
                if not _has_remote_seat_capacity(
                    remote_user_count=remote_user_count,
                    seat_limit=seat_limit,
                    replacing=True,
                ):
                    return {
                        "status": "waiting",
                        "reason": "replacement_overlap_cap_reached",
                        "remote_user_count": remote_user_count,
                        "remote_member_count": remote_member_count,
                        "replacement_cap": replacement_cap,
                        "invite_reconcile": invite_result,
                    }
                replaces_credential_id = replacement_credential_id
            else:
                if not _has_remote_seat_capacity(
                    remote_user_count=remote_user_count,
                    seat_limit=seat_limit,
                    replacing=False,
                ):
                    return {
                        "status": "healthy",
                        "remote_user_count": remote_user_count,
                        "remote_member_count": remote_member_count,
                        "seat_limit": seat_limit,
                        "invite_reconcile": invite_result,
                    }
                replaces_credential_id = ""

            candidate = session.scalars(
                select(SpaceReplenishEmailModel)
                .where(
                    SpaceReplenishEmailModel.space_id == space_id,
                    SpaceReplenishEmailModel.invite_status == "confirmed",
                    SpaceReplenishEmailModel.process_status.in_(("idle", "failed")),
                )
                .order_by(
                    SpaceReplenishEmailModel.retry_count.asc(),
                    SpaceReplenishEmailModel.invite_confirmed_at.asc(),
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            ).first()
            if candidate is None:
                return {
                    "status": "waiting",
                    "reason": "no_confirmed_invite_candidate",
                    "remote_user_count": remote_user_count,
                    "remote_member_count": remote_member_count,
                    "invite_reconcile": invite_result,
                }
            candidate.process_status = "provisioning"
            candidate.replaces_space_credential_id = replaces_credential_id
            candidate.processing_started_at = datetime.now(UTC)
            candidate.retry_count += 1
            candidate.failure_code = ""
            candidate.failure_message = ""
            candidate.updated_at = datetime.now(UTC)
            candidate_id = candidate.id
            session.commit()

        try:
            provision = self._provision_candidate(
                row_id=candidate_id,
                run_id=run_id,
                work_id=work_id,
            )
        except Exception as exc:
            self._mark_candidate_failed(row_id=candidate_id, error=exc)
            raise
        push_result = self._push_credential(str(provision["space_credential_id"]))
        removal_result = self._complete_and_remove_replacement(
            space_id=space_id,
            run_id=run_id,
        )
        if removal_result is not None:
            return {
                **removal_result,
                "remote_user_count": remote_user_count,
                "remote_member_count": remote_member_count,
                "provision": provision,
                "push": push_result,
                "invite_reconcile": invite_result,
            }
        return {
            "status": "provisioned",
            "remote_user_count": remote_user_count,
            "remote_member_count": remote_member_count,
            "provision": provision,
            "push": push_result,
            "invite_reconcile": invite_result,
        }

    def _select_invite_candidates(
        self,
        *,
        session: Session,
        limit: int,
    ) -> list[SpaceReplenishEmailModel]:
        return list(
            session.scalars(
                select(SpaceReplenishEmailModel)
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
                            func.lower(UserAccountModel.email) == SpaceReplenishEmailModel.email_key
                        )
                    ),
                )
                .order_by(SpaceReplenishEmailModel.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(limit)
            ).all()
        )

    def _release_reserved_invites(self, *, reserved_ids: list[str], error: Exception) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            rows = session.scalars(
                select(SpaceReplenishEmailModel).where(
                    SpaceReplenishEmailModel.id.in_(reserved_ids),
                    SpaceReplenishEmailModel.invite_status == "reserved",
                )
            ).all()
            for row in rows:
                row.space_id = None
                row.invite_status = "available"
                row.failure_code = "invite_executor_submit_failed"
                row.failure_message = f"{type(error).__name__}: {error}"[:1000]
                row.updated_at = now
            session.commit()

    def _admin_context(self, *, space_id: str, bind_reason: str) -> _AdminContext:
        with self._session_factory() as session:
            space = _active_business_space(session=session, space_id=space_id)
            admin = _admin_session(session=session, space=space)
            if admin is None or not admin.access_token:
                raise SpaceAutoReplenishError("team admin session missing access token")
            proxy_url = ensure_team_admin_static_proxy_url_in_session(
                session=session,
                team_admin_session_id=admin.id,
                bind_reason=bind_reason,
            )
            context = _AdminContext(
                space_id=space.id,
                external_space_id=space.external_space_id,
                access_token=admin.access_token,
                cookie_header=admin.cookie_header,
                proxy_url=proxy_url,
            )
            session.commit()
            return context

    def _refresh_pushed_usage(self, *, space_id: str, run_id: str) -> None:
        with self._session_factory() as session:
            credential_ids = list(
                session.scalars(
                    select(SpaceCredentialModel.id)
                    .join(
                        SpacePushBindingModel,
                        SpacePushBindingModel.space_credential_id == SpaceCredentialModel.id,
                    )
                    .where(
                        SpaceCredentialModel.space_id == space_id,
                        SpaceCredentialModel.credential_status == "active",
                        SpacePushBindingModel.push_status == "pushed",
                    )
                ).all()
            )
        workflow = SpaceRecycleSweepWorkflow(
            session_factory=self._session_factory,
            openai_provider=self._openai_provider,
        )
        for credential_id in credential_ids:
            try:
                workflow.refresh_binding_usage(space_credential_id=credential_id)
            except Exception as exc:
                self._event(
                    run_id=run_id,
                    event_type="space_auto_replenish.usage_failed",
                    message="credential usage refresh failed",
                    level="ERROR",
                    data_json={
                        "space_id": space_id,
                        "space_credential_id": credential_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )

    def _active_unpushed_credential_id(self, *, space_id: str) -> str:
        with self._session_factory() as session:
            return str(
                session.scalar(
                    select(SpaceCredentialModel.id)
                    .outerjoin(
                        SpacePushBindingModel,
                        SpacePushBindingModel.space_credential_id == SpaceCredentialModel.id,
                    )
                    .where(
                        SpaceCredentialModel.space_id == space_id,
                        SpaceCredentialModel.credential_status == "active",
                        or_(
                            SpacePushBindingModel.space_credential_id.is_(None),
                            SpacePushBindingModel.push_status.in_(
                                ("none", "pending", "pushing", "failed", "skipped")
                            ),
                        ),
                    )
                    .order_by(SpaceCredentialModel.created_at.asc())
                    .limit(1)
                )
                or ""
            )

    def _push_credential(self, credential_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            credential = session.get(SpaceCredentialModel, credential_id)
            if credential is None:
                raise SpaceAutoReplenishError("space credential disappeared before push")
            space = session.get(SpaceModel, credential.space_id)
            binding = session.get(SpacePushBindingModel, credential.id)
            if space is None:
                raise SpaceAutoReplenishError("space disappeared before push")
            if binding is not None and binding.push_status == "pushed":
                return {"status": "pushed", "downstream_channel_id": binding.downstream_channel_id}
            if binding is not None and binding.downstream_channel_id:
                channel_ids = [binding.downstream_channel_id]
                is_retry = binding.push_status == "failed"
            else:
                channel_ids = list(
                    session.scalars(
                        select(DownstreamChannelModel.id)
                        .where(DownstreamChannelModel.enabled.is_(True))
                        .order_by(DownstreamChannelModel.created_at.asc())
                    ).all()
                )
                is_retry = False
        errors: list[str] = []
        for channel_id in channel_ids:
            with self._session_factory() as session:
                channel = session.get(DownstreamChannelModel, channel_id)
                if channel is None:
                    continue
                provider = provider_from_channel(channel)
            try:
                SpaceDirectPushWorkflow(
                    session_factory=self._session_factory,
                    downstream_provider=provider,
                ).run(
                    SpaceDirectPushInput(
                        space_credential_id=credential_id,
                        downstream_channel_id=channel_id,
                        is_retry=is_retry,
                    )
                )
                return {"status": "pushed", "downstream_channel_id": channel_id}
            except SpaceDirectPushWorkflowError as exc:
                errors.append(f"{channel_id}:{exc}")
                with self._session_factory() as session:
                    binding = session.get(SpacePushBindingModel, credential_id)
                    if binding is not None:
                        break
        return {"status": "waiting", "errors": errors}

    def _complete_pushed_candidates(self, *, space_id: str, run_id: str) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            rows = session.scalars(
                select(SpaceReplenishEmailModel)
                .join(
                    SpacePushBindingModel,
                    SpacePushBindingModel.space_credential_id
                    == SpaceReplenishEmailModel.space_credential_id,
                )
                .where(
                    SpaceReplenishEmailModel.space_id == space_id,
                    SpaceReplenishEmailModel.process_status == "credential_created",
                    SpacePushBindingModel.push_status == "pushed",
                )
            ).all()
            for row in rows:
                if row.replaces_space_credential_id:
                    settlement = manually_settle_pushed_binding_from_usage_state(
                        session=session,
                        space_credential_id=row.replaces_space_credential_id,
                    )
                    if settlement.push_status != "used":
                        row.failure_code = "replacement_old_credential_not_settled"
                        row.failure_message = settlement.reason
                        row.updated_at = now
                        continue
                    row.process_status = "remove_pending"
                else:
                    row.process_status = "completed"
                    row.completed_at = now
                row.failure_code = ""
                row.failure_message = ""
                row.updated_at = now
            session.commit()

    def _complete_and_remove_replacement(
        self,
        *,
        space_id: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        self._complete_pushed_candidates(space_id=space_id, run_id=run_id)
        remove_row_id = self._pending_removal_row_id(space_id=space_id)
        if not remove_row_id:
            return None
        return self._remove_replaced_member(row_id=remove_row_id, run_id=run_id)

    def _pending_removal_row_id(self, *, space_id: str) -> str:
        with self._session_factory() as session:
            return str(
                session.scalar(
                    select(SpaceReplenishEmailModel.id)
                    .where(
                        SpaceReplenishEmailModel.space_id == space_id,
                        SpaceReplenishEmailModel.process_status == "remove_pending",
                    )
                    .order_by(SpaceReplenishEmailModel.updated_at.asc())
                    .limit(1)
                )
                or ""
            )

    def _provisioning_row_id(self, *, space_id: str) -> str:
        with self._session_factory() as session:
            return str(
                session.scalar(
                    select(SpaceReplenishEmailModel.id)
                    .where(
                        SpaceReplenishEmailModel.space_id == space_id,
                        SpaceReplenishEmailModel.process_status == "provisioning",
                    )
                    .order_by(SpaceReplenishEmailModel.processing_started_at.asc())
                    .limit(1)
                )
                or ""
            )

    def _remove_replaced_member(self, *, row_id: str, run_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(SpaceReplenishEmailModel, row_id)
            if row is None or not row.replaces_space_credential_id:
                raise SpaceAutoReplenishError("replacement removal state is incomplete")
            old_credential = session.get(SpaceCredentialModel, row.replaces_space_credential_id)
            if old_credential is None:
                raise SpaceAutoReplenishError("replaced credential not found")
            account = session.get(UserAccountModel, old_credential.user_account_id)
            membership = session.scalar(
                select(SpaceMembershipModel).where(
                    SpaceMembershipModel.space_id == row.space_id,
                    SpaceMembershipModel.user_account_id == old_credential.user_account_id,
                )
            )
            if account is None or membership is None:
                raise SpaceAutoReplenishError("replaced member local state not found")
            old_user_account_id = old_credential.user_account_id
            old_credential_id = old_credential.id
            remote_user_id = str(
                membership.remote_user_id or membership.remote_account_user_id or ""
            ).strip()
            if not remote_user_id:
                raise SpaceAutoReplenishError("replaced member has no remote user id")
            email = account.email
            space_id = str(row.space_id or "")

        context = self._admin_context(
            space_id=space_id,
            bind_reason="space_auto_replenish_remove_member",
        )
        delete_error = ""
        try:
            self._openai_provider.remove_account_user(
                access_token=context.access_token,
                account_id=context.external_space_id,
                user_id=remote_user_id,
                cookie_header=context.cookie_header,
                proxy_url=context.proxy_url,
            )
        except Exception as exc:
            delete_error = f"{type(exc).__name__}: {exc}"
        try:
            remote_members = self._openai_provider.list_account_users(
                access_token=context.access_token,
                account_id=context.external_space_id,
                cookie_header=context.cookie_header,
                page_size=100,
                proxy_url=context.proxy_url,
            )
        except Exception as exc:
            self._mark_remove_waiting(
                row_id=row_id,
                code="remote_users_confirm_failed",
                message=f"{type(exc).__name__}: {exc}",
            )
            return {"status": "remove_pending", "reason": "remote_users_confirm_failed"}
        if _remote_member_present(
            members=remote_members,
            email=email,
            remote_user_id=remote_user_id,
        ):
            self._mark_remove_waiting(
                row_id=row_id,
                code="remote_member_still_present",
                message=delete_error or "remote member is still present after delete",
            )
            return {"status": "remove_pending", "reason": "remote_member_still_present"}

        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(SpaceReplenishEmailModel, row_id)
            old_credential = session.get(SpaceCredentialModel, old_credential_id)
            membership = session.scalar(
                select(SpaceMembershipModel).where(
                    SpaceMembershipModel.space_id == space_id,
                    SpaceMembershipModel.user_account_id == old_user_account_id,
                )
            )
            if membership is not None:
                session.delete(membership)
            if old_credential is not None:
                old_credential.credential_status = "revoked"
                old_credential.failure_code = ""
                old_credential.failure_message = ""
                old_credential.updated_at = now
            if row is not None:
                row.process_status = "completed"
                row.completed_at = now
                row.failure_code = ""
                row.failure_message = ""
                row.updated_at = now
            session.commit()
        self._event(
            run_id=run_id,
            event_type="space_auto_replenish.member_removed",
            message="replaced remote member removed and local membership deleted",
            data_json={
                "space_id": space_id,
                "email": email,
                "remote_user_id": remote_user_id,
                "revoked_space_credential_id": old_credential_id,
            },
        )
        return {"status": "completed", "removed_email": email}

    def _mark_remove_waiting(self, *, row_id: str, code: str, message: str) -> None:
        with self._session_factory() as session:
            row = session.get(SpaceReplenishEmailModel, row_id)
            if row is not None:
                row.failure_code = code
                row.failure_message = message[:1000]
                row.updated_at = datetime.now(UTC)
            session.commit()

    def _provision_candidate(
        self,
        *,
        row_id: str,
        run_id: str,
        work_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(SpaceReplenishEmailModel, row_id)
            if row is None or row.process_status != "provisioning" or not row.space_id:
                raise SpaceAutoReplenishError("candidate is not in provisioning state")
            space = _active_business_space(session=session, space_id=row.space_id)
            account = (
                session.get(UserAccountModel, row.user_account_id) if row.user_account_id else None
            )
            if account is None:
                account = session.scalar(
                    select(UserAccountModel).where(
                        func.lower(UserAccountModel.email) == row.email_key
                    )
                )
            email = row.email
            space_id = space.id
            external_space_id = space.external_space_id

        if account is not None:
            if account.account_status != "active":
                raise SpaceAutoReplenishError("candidate account is not active")
            user_account_id = BackfillSessionWorkflow(
                session_factory=self._session_factory,
                mail_provider=self._mail_provider,
                totp_code_resolver=self._totp_code_resolver,
            ).run(user_account_id=account.id, run_id=run_id)
        else:
            registration = ProtocolRegistrationWorkflow(
                session_factory=self._session_factory,
                mail_provider=self._mail_provider,
            ).run(
                ProtocolRegistrationInput(
                    mode=EMAIL_PROTOCOL_NO_PHONE,
                    fixed_email=email,
                    use_proxy=True,
                    proxy_country=self._registration_proxy_country,
                    mail_provider="outlook",
                    project_key="space-auto-replenish",
                    caller_id="space-auto-replenish",
                ),
                work_id=work_id,
                run_id=run_id,
            )
            user_account_id = str(registration.get("user_account_id") or "")
            if not user_account_id:
                raise SpaceAutoReplenishError("fixed email registration returned no account id")

        with self._session_factory() as session:
            membership = session.scalar(
                select(SpaceMembershipModel).where(
                    SpaceMembershipModel.space_id == space_id,
                    SpaceMembershipModel.user_account_id == user_account_id,
                    SpaceMembershipModel.membership_status == "active",
                    SpaceMembershipModel.session_account_detected.is_(True),
                )
            )
            account = session.get(UserAccountModel, user_account_id)
            space = session.get(SpaceModel, space_id)
            if membership is None:
                raise SpaceAutoReplenishError(
                    "session completed but target business space was not detected"
                )
            if account is None or space is None:
                raise SpaceAutoReplenishError("candidate account or space disappeared")
            cookie_header = _web_session_cookie_header(account)
            proxy_url = ensure_account_proxy_url(
                self._session_factory,
                user_account_id,
                bind_reason="space_auto_replenish_business_access_token",
            )

        def create_credential() -> str:
            return CreateBusinessAccessTokenCredentialWorkflow(
                session_factory=self._session_factory,
                openai_provider=self._openai_provider,
            ).run(
                CreateBusinessAccessTokenCredentialInput(
                    user_account_id=user_account_id,
                    external_space_id=external_space_id,
                    session_access_token="",
                    credential_name=f"codex-{email}",
                    cookie_header=cookie_header,
                    space_name=space.name,
                    owner_user_account_id=space.owner_user_account_id,
                    source_admin_session_id=space.source_admin_session_id,
                    proxy_url=proxy_url,
                )
            )

        credential_id = run_business_access_token_rate_limited(
            external_space_id=external_space_id,
            callback=create_credential,
        )
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(SpaceReplenishEmailModel, row_id)
            if row is None:
                raise SpaceAutoReplenishError("candidate state disappeared after authorization")
            row.user_account_id = user_account_id
            row.space_credential_id = credential_id
            row.process_status = "credential_created"
            row.failure_code = ""
            row.failure_message = ""
            row.updated_at = now
            session.commit()
        return {
            "email": email,
            "user_account_id": user_account_id,
            "space_credential_id": credential_id,
        }

    def _mark_candidate_failed(self, *, row_id: str, error: Exception) -> None:
        with self._session_factory() as session:
            row = session.get(SpaceReplenishEmailModel, row_id)
            if row is not None:
                row.process_status = "failed"
                row.failure_code = type(error).__name__[:200]
                row.failure_message = str(error)[:1000]
                row.updated_at = datetime.now(UTC)
            session.commit()

    def _event(
        self,
        *,
        run_id: str,
        event_type: str,
        message: str,
        data_json: dict[str, Any],
        level: str = "INFO",
    ) -> None:
        if not run_id:
            return
        with self._session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type=event_type,
                message=message,
                level=level,
                data_json=data_json,
            )
            session.commit()


def import_space_replenish_emails(
    *,
    session_factory: Callable[[], Session],
    emails: Sequence[str],
) -> dict[str, int]:
    normalized = _normalized_emails(emails)
    now = datetime.now(UTC)
    inserted = 0
    existing = 0
    with session_factory() as session:
        existing_keys = set(
            session.scalars(
                select(SpaceReplenishEmailModel.email_key).where(
                    SpaceReplenishEmailModel.email_key.in_(list(normalized))
                )
            ).all()
        )
        for email_key, email in normalized.items():
            if email_key in existing_keys:
                existing += 1
                continue
            session.add(
                SpaceReplenishEmailModel(
                    id=f"space-replenish-email-{uuid4()}",
                    email=email,
                    email_key=email_key,
                    source_type="local_inventory",
                    invite_status="available",
                    process_status="idle",
                    created_at=now,
                    updated_at=now,
                )
            )
            inserted += 1
        session.commit()
    return {"requested": len(normalized), "inserted": inserted, "existing": existing}


def _active_business_space(
    *,
    session: Session,
    space_id: str,
    lock: bool = False,
) -> SpaceModel:
    space = session.get(
        SpaceModel,
        str(space_id or "").strip(),
        with_for_update=lock,
    )
    if space is None:
        raise SpaceAutoReplenishError("space not found")
    if space.space_type != "business" or space.space_status != "active":
        raise SpaceAutoReplenishError("auto replenish requires an active business space")
    if space.credential_type not in {"team_5h_weekly", "team_monthly"}:
        raise SpaceAutoReplenishError("unsupported business credential type")
    if not space.external_space_id:
        raise SpaceAutoReplenishError("business space has no external space id")
    return space


def _admin_session(*, session: Session, space: SpaceModel) -> TeamAdminSessionModel | None:
    if not space.source_admin_session_id:
        return None
    return session.get(TeamAdminSessionModel, space.source_admin_session_id)


def _normalized_emails(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        email = str(value or "").strip()
        if not email or "@" not in email:
            continue
        result.setdefault(email.casefold(), email)
    return result


def _remote_invite_email(item: dict) -> str:
    for key in ("email", "email_address", "emailAddress", "recipient_email"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    user = item.get("user")
    return str(user.get("email") or "").strip() if isinstance(user, dict) else ""


def _replacement_required_credential_id(*, session: Session, space: SpaceModel) -> str:
    window = "weekly" if space.credential_type == "team_5h_weekly" else "monthly"
    existing_replacements = select(SpaceReplenishEmailModel.replaces_space_credential_id).where(
        SpaceReplenishEmailModel.space_id == space.id,
        SpaceReplenishEmailModel.replaces_space_credential_id != "",
        SpaceReplenishEmailModel.process_status.in_(
            ("provisioning", "credential_created", "remove_pending")
        ),
    )
    return str(
        session.scalar(
            select(SpaceCredentialModel.id)
            .join(
                SpacePushBindingModel,
                SpacePushBindingModel.space_credential_id == SpaceCredentialModel.id,
            )
            .join(
                SpaceCredentialUsageStateModel,
                SpaceCredentialUsageStateModel.space_credential_id == SpaceCredentialModel.id,
            )
            .where(
                SpaceCredentialModel.space_id == space.id,
                SpaceCredentialModel.credential_status == "active",
                SpacePushBindingModel.push_status == "pushed",
                SpaceCredentialUsageStateModel.quota_window_kind == window,
                SpaceCredentialUsageStateModel.usage_percent >= REPLACEMENT_USAGE_PERCENT,
                ~SpaceCredentialModel.id.in_(existing_replacements),
            )
            .order_by(SpaceCredentialUsageStateModel.usage_percent.desc())
            .limit(1)
        )
        or ""
    )


def _web_session_cookie_header(account: UserAccountModel) -> str:
    cookie_header = str(account.cookie_header or "").strip()
    session_token = str(account.session_token or "").strip()
    if not session_token or "__Secure-next-auth.session-token=" in cookie_header:
        return cookie_header
    session_cookie = f"__Secure-next-auth.session-token={session_token}"
    return f"{session_cookie}; {cookie_header}" if cookie_header else session_cookie


def _remote_member_present(*, members: list[dict], email: str, remote_user_id: str) -> bool:
    email_key = email.strip().casefold()
    for member in members:
        if email_key and _remote_member_email(member).casefold() == email_key:
            return True
        if remote_user_id and remote_user_id in _remote_member_ids(member):
            return True
    return False


def _remote_member_email(member: dict) -> str:
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


def _remote_member_ids(member: dict) -> set[str]:
    values = {
        str(member.get(key) or "").strip()
        for key in ("id", "user_id", "userId", "account_user_id", "accountUserId")
    }
    user = member.get("user")
    if isinstance(user, dict):
        values.update(str(user.get(key) or "").strip() for key in ("id", "user_id", "userId"))
    return {value.split("__", 1)[0] for value in values if value}
