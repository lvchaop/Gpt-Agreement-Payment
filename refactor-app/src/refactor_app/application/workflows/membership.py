from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic, sleep
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from refactor_app.domain.enums import InvitePermission, MembershipStatus, SeatStatus
from refactor_app.infrastructure.db.models import (
    CodexOAuthCredentialModel,
    MembershipModel,
    ProxyInventoryModel,
    TeamAdminSessionModel,
    TeamWorkspaceModel,
    UserAccountAuthModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
    WorkItemModel,
)
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.contracts import OpenAIChatGPTProvider


class MembershipWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class MembershipProbeResult:
    membership_status: str
    invite_permission: str
    user_count: int
    invite_count: int
    seat_status: str
    can_invite: bool


class MembershipProbeWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider

    def run(self, *, membership_id: str) -> MembershipProbeResult:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if uow.memberships is None:
                raise MembershipWorkflowError("membership repository is not initialized")
            if uow.team_workspaces is None:
                raise MembershipWorkflowError("team workspace repository is not initialized")

            membership = uow.memberships.get(membership_id)
            if membership is None:
                raise MembershipWorkflowError(f"membership not found: {membership_id}")

            workspace = uow.team_workspaces.get(membership.team_workspace_id)
            if workspace is None:
                raise MembershipWorkflowError(
                    f"team workspace not found: {membership.team_workspace_id}"
                )
            if not membership.chatgpt_web_backend_access_token:
                raise MembershipWorkflowError("membership missing chatgpt web backend access token")

            payload = self._openai_provider.probe_membership(
                access_token=membership.chatgpt_web_backend_access_token,
                team_id=workspace.external_workspace_id,
            )
            result = apply_membership_probe(membership, workspace, payload, now)
            return result


class InviteWorkspaceMemberWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider

    def run(self, *, inviter_membership_id: str, email: str) -> dict:
        if not email:
            raise MembershipWorkflowError("email is required")
        with UnitOfWork(self._session_factory) as uow:
            if uow.memberships is None:
                raise MembershipWorkflowError("membership repository is not initialized")
            if uow.team_workspaces is None:
                raise MembershipWorkflowError("team workspace repository is not initialized")
            membership = uow.memberships.get(inviter_membership_id)
            if membership is None:
                raise MembershipWorkflowError(f"membership not found: {inviter_membership_id}")
            workspace = uow.team_workspaces.get(membership.team_workspace_id)
            if workspace is None:
                raise MembershipWorkflowError(
                    f"team workspace not found: {membership.team_workspace_id}"
                )
            if not membership.chatgpt_web_backend_access_token:
                raise MembershipWorkflowError("membership missing chatgpt web backend access token")
            return self._openai_provider.invite_member(
                access_token=membership.chatgpt_web_backend_access_token,
                team_id=workspace.external_workspace_id,
                email=email,
            )

    def run_admin_invite(
        self,
        *,
        team_workspace_id: str,
        user_account_id: str,
        team_admin_session_id: str = "",
        barrier_key: str = "",
        barrier_group: str = "",
        barrier_expected: int = 0,
        barrier_timeout_s: float = 30,
        run_id: str = "",
        work_id: str = "",
    ) -> dict:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            workspace = session.get(TeamWorkspaceModel, team_workspace_id)
            if workspace is None:
                raise MembershipWorkflowError(f"team workspace not found: {team_workspace_id}")
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise MembershipWorkflowError(f"user account not found: {user_account_id}")
            admin_session = _load_admin_session(
                session=session,
                team_admin_session_id=team_admin_session_id,
                source_admin_session_id=workspace.source_admin_session_id,
            )
            if admin_session is None or not admin_session.access_token:
                raise MembershipWorkflowError("team admin session missing access token")

            _wait_before_invite_request(
                session=session,
                barrier_key=barrier_key,
                barrier_group=barrier_group,
                expected=barrier_expected,
                timeout_s=barrier_timeout_s,
                run_id=run_id,
                work_id=work_id,
            )
            payload = self._openai_provider.invite_member(
                access_token=admin_session.access_token,
                team_id=workspace.external_workspace_id,
                email=account.email,
                cookie_header=admin_session.cookie_header,
                seat_type=_invite_seat_type(workspace.plan_type),
            )
            membership = session.query(MembershipModel).filter_by(
                user_account_id=user_account_id,
                team_workspace_id=team_workspace_id,
            ).one_or_none()
            if membership is None:
                membership = MembershipModel(
                    id=f"membership-{user_account_id}-{team_workspace_id}",
                    user_account_id=user_account_id,
                    team_workspace_id=team_workspace_id,
                    role="standard-user",
                    membership_status=MembershipStatus.INVITED.value,
                    invite_permission="unknown",
                    user_count=0,
                    invite_count=0,
                    seat_status="unknown",
                    can_invite=False,
                    created_at=now,
                    updated_at=now,
                )
                session.add(membership)
            else:
                membership.membership_status = MembershipStatus.INVITED.value
                membership.role = membership.role or "standard-user"
                membership.failure_code = ""
                membership.failure_message = ""
                membership.updated_at = now
            session.commit()
            return {
                "membership_id": membership.id,
                "user_account_id": user_account_id,
                "team_workspace_id": team_workspace_id,
                "email": account.email,
                "invite": payload,
            }


class AcceptWorkspaceInviteWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider

    def run(
        self,
        *,
        membership_id: str,
        barrier_key: str = "",
        barrier_group: str = "",
        barrier_expected: int = 0,
        barrier_timeout_s: float = 30,
        run_id: str = "",
        work_id: str = "",
    ) -> dict:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            membership = session.get(MembershipModel, membership_id)
            if membership is None:
                raise MembershipWorkflowError(f"membership not found: {membership_id}")
            workspace = session.get(TeamWorkspaceModel, membership.team_workspace_id)
            if workspace is None:
                raise MembershipWorkflowError(
                    f"team workspace not found: {membership.team_workspace_id}"
                )
            access_token, device_id = _member_accept_auth(session=session, membership=membership)
            if not access_token:
                _mark_membership_failed(
                    membership,
                    now=now,
                    code="missing_member_access_token",
                    message="member account has no saved access token for accepting invite",
                )
                session.commit()
                raise MembershipWorkflowError("member account missing access token")
            proxy = _active_account_proxy(
                session=session,
                user_account_id=membership.user_account_id,
            )
            if proxy is None:
                _mark_membership_failed(
                    membership,
                    now=now,
                    code="missing_account_proxy",
                    message="member account has no active proxy binding for accepting invite",
                )
                session.commit()
                raise MembershipWorkflowError("member account missing active proxy")

            _wait_before_accept_request(
                session=session,
                barrier_key=barrier_key,
                barrier_group=barrier_group,
                expected=barrier_expected,
                timeout_s=barrier_timeout_s,
                run_id=run_id,
                work_id=work_id,
            )
            payload = self._openai_provider.accept_invite(
                access_token=access_token,
                team_id=workspace.external_workspace_id,
                proxy_url=_proxy_url(proxy),
                device_id=device_id,
            )
            membership.membership_status = MembershipStatus.ACTIVE.value
            membership.chatgpt_web_backend_access_token = access_token
            membership.chatgpt_web_backend_access_token_status = "active"
            membership.failure_code = ""
            membership.failure_message = ""
            membership.updated_at = now
            session.commit()
            return {
                "membership_id": membership.id,
                "user_account_id": membership.user_account_id,
                "team_workspace_id": membership.team_workspace_id,
                "accept": payload,
            }


def apply_membership_probe(
    membership: MembershipModel,
    workspace: TeamWorkspaceModel,
    payload: dict,
    now: datetime,
) -> MembershipProbeResult:
    membership_status = _membership_status(payload)
    invite_permission = _invite_permission(payload)
    user_count = _non_negative_int(payload.get("user_count", payload.get("userCount", 0)))
    invite_count = _non_negative_int(payload.get("invite_count", payload.get("inviteCount", 0)))
    seat_status = _seat_status(
        user_count=user_count,
        invite_count=invite_count,
        seat_limit=workspace.seat_limit,
    )
    can_invite = (
        workspace.workspace_status == "active"
        and membership_status == MembershipStatus.ACTIVE.value
        and invite_permission == InvitePermission.OK.value
        and seat_status == SeatStatus.AVAILABLE.value
    )

    membership.membership_status = membership_status
    membership.invite_permission = invite_permission
    membership.user_count = user_count
    membership.invite_count = invite_count
    membership.seat_status = seat_status
    membership.can_invite = can_invite
    membership.last_probe_status = "ok"
    membership.last_probe_at = now
    membership.updated_at = now

    return MembershipProbeResult(
        membership_status=membership_status,
        invite_permission=invite_permission,
        user_count=user_count,
        invite_count=invite_count,
        seat_status=seat_status,
        can_invite=can_invite,
    )


def _load_admin_session(
    *,
    session: Session,
    team_admin_session_id: str,
    source_admin_session_id: str,
) -> TeamAdminSessionModel | None:
    if team_admin_session_id:
        return session.get(TeamAdminSessionModel, team_admin_session_id)
    if source_admin_session_id:
        found = session.get(TeamAdminSessionModel, source_admin_session_id)
        if found is not None:
            return found
    return (
        session.query(TeamAdminSessionModel)
        .order_by(TeamAdminSessionModel.imported_at.desc())
        .first()
    )


def _membership_status(payload: dict) -> str:
    raw = str(payload.get("membership_status") or payload.get("membershipStatus") or "active")
    if raw not in {item.value for item in MembershipStatus}:
        return MembershipStatus.FAILED.value
    return raw


def _invite_permission(payload: dict) -> str:
    if bool(payload.get("noInvitePermission")):
        return InvitePermission.NO_PERMISSION.value
    raw = str(payload.get("invite_permission") or payload.get("invitePermission") or "")
    if raw in {item.value for item in InvitePermission}:
        return raw
    if raw == "":
        return InvitePermission.OK.value
    return InvitePermission.ERROR.value


def _seat_status(*, user_count: int, invite_count: int, seat_limit: int) -> str:
    if seat_limit <= 0:
        return SeatStatus.UNKNOWN.value
    if user_count + invite_count >= seat_limit:
        return SeatStatus.FULL.value
    return SeatStatus.AVAILABLE.value


def _non_negative_int(value: object) -> int:
    parsed = int(value or 0)
    if parsed < 0:
        raise MembershipWorkflowError("probe count fields must be non-negative")
    return parsed


def _member_accept_auth(*, session: Session, membership: MembershipModel) -> tuple[str, str]:
    auth = session.get(UserAccountAuthModel, membership.user_account_id)
    device_id = auth.device_id if auth is not None else ""
    if membership.chatgpt_web_backend_access_token:
        return membership.chatgpt_web_backend_access_token, device_id
    if auth is not None and auth.access_token:
        return auth.access_token, device_id
    credential = session.scalars(
        select(CodexOAuthCredentialModel)
        .where(
            CodexOAuthCredentialModel.user_account_id == membership.user_account_id,
            CodexOAuthCredentialModel.team_workspace_id == membership.team_workspace_id,
            CodexOAuthCredentialModel.credential_status == "active",
            CodexOAuthCredentialModel.access_token != "",
        )
        .order_by(CodexOAuthCredentialModel.updated_at.desc())
        .limit(1)
    ).first()
    return (credential.access_token, device_id) if credential is not None else ("", device_id)


def _active_account_proxy(
    *,
    session: Session,
    user_account_id: str,
) -> ProxyInventoryModel | None:
    row = session.execute(
        select(UserAccountProxyBindingModel, ProxyInventoryModel)
        .join(ProxyInventoryModel, ProxyInventoryModel.id == UserAccountProxyBindingModel.proxy_id)
        .where(
            UserAccountProxyBindingModel.user_account_id == user_account_id,
            UserAccountProxyBindingModel.bind_status == "active",
        )
        .limit(1)
    ).first()
    if row is None:
        return None
    _binding, proxy = row
    return proxy


def _proxy_url(proxy: ProxyInventoryModel) -> str:
    scheme = proxy.proxy_scheme or "http"
    host = proxy.proxy_host
    port = proxy.proxy_port
    if proxy.proxy_username:
        username = quote(proxy.proxy_username, safe="")
        password = quote(proxy.proxy_password or "", safe="")
        return f"{scheme}://{username}:{password}@{host}:{port}"
    return f"{scheme}://{host}:{port}"


def _mark_membership_failed(
    membership: MembershipModel,
    *,
    now: datetime,
    code: str,
    message: str,
) -> None:
    membership.membership_status = MembershipStatus.FAILED.value
    membership.failure_code = code
    membership.failure_message = message
    membership.updated_at = now


def _invite_seat_type(plan_type: str) -> str:
    normalized = (plan_type or "").strip().lower()
    if normalized in {"team", "chatgptteamplan"} or "team" in normalized:
        return "default"
    return "usage_based"


def _wait_before_invite_request(
    *,
    session: Session,
    barrier_key: str,
    barrier_group: str,
    expected: int,
    timeout_s: float,
    run_id: str,
    work_id: str,
) -> None:
    if not barrier_key or not barrier_group or expected <= 1:
        return

    if work_id:
        work = session.get(WorkItemModel, work_id)
        if work is not None:
            updated_input = dict(work.input_json)
            updated_input["_invite_request_barrier_reached"] = True
            work.input_json = updated_input
            work.updated_at = datetime.now(UTC)

    started = monotonic()
    if run_id:
        EventWriter(session).write(
            run_id=run_id,
            event_type="membership.invite.barrier_waiting",
            message="invite work reached request barrier",
            data_json={
                "work_id": work_id,
                "barrier_key": barrier_key,
                "barrier_group": barrier_group,
                "barrier_expected": expected,
            },
        )
        session.commit()

    while True:
        arrived = _invite_barrier_arrived_count(
            session=session,
            barrier_key=barrier_key,
            barrier_group=barrier_group,
        )
        if arrived >= expected:
            if run_id:
                EventWriter(session).write(
                    run_id=run_id,
                    event_type="membership.invite.barrier_released",
                    message="invite request barrier released",
                    data_json={
                        "work_id": work_id,
                        "barrier_key": barrier_key,
                        "barrier_group": barrier_group,
                        "barrier_expected": expected,
                        "barrier_arrived": arrived,
                    },
                )
                session.commit()
            return
        if monotonic() - started >= timeout_s:
            raise TimeoutError(
                "invite request barrier timeout: "
                f"key={barrier_key} group={barrier_group} arrived={arrived} expected={expected}"
            )
        session.rollback()
        sleep(0.1)


def _wait_before_accept_request(
    *,
    session: Session,
    barrier_key: str,
    barrier_group: str,
    expected: int,
    timeout_s: float,
    run_id: str,
    work_id: str,
) -> None:
    if not barrier_key or not barrier_group or expected <= 1:
        return

    if work_id:
        work = session.get(WorkItemModel, work_id)
        if work is not None:
            updated_input = dict(work.input_json)
            updated_input["_accept_request_barrier_reached"] = True
            work.input_json = updated_input
            work.updated_at = datetime.now(UTC)

    started = monotonic()
    if run_id:
        EventWriter(session).write(
            run_id=run_id,
            event_type="membership.accept.barrier_waiting",
            message="accept invite work reached request barrier",
            data_json={
                "work_id": work_id,
                "barrier_key": barrier_key,
                "barrier_group": barrier_group,
                "barrier_expected": expected,
            },
        )
        session.commit()

    while True:
        arrived = _accept_barrier_arrived_count(
            session=session,
            barrier_key=barrier_key,
            barrier_group=barrier_group,
        )
        if arrived >= expected:
            if run_id:
                EventWriter(session).write(
                    run_id=run_id,
                    event_type="membership.accept.barrier_released",
                    message="accept invite request barrier released",
                    data_json={
                        "work_id": work_id,
                        "barrier_key": barrier_key,
                        "barrier_group": barrier_group,
                        "barrier_expected": expected,
                        "barrier_arrived": arrived,
                    },
                )
                session.commit()
            return
        if monotonic() - started >= timeout_s:
            raise TimeoutError(
                "accept invite request barrier timeout: "
                f"key={barrier_key} group={barrier_group} arrived={arrived} expected={expected}"
            )
        session.rollback()
        sleep(0.1)


def _invite_barrier_arrived_count(
    *,
    session: Session,
    barrier_key: str,
    barrier_group: str,
) -> int:
    stmt = (
        select(func.count())
        .select_from(WorkItemModel)
        .where(
            WorkItemModel.input_json["_barrier_key"].as_string() == barrier_key,
            WorkItemModel.input_json["_barrier_group"].as_string() == barrier_group,
            WorkItemModel.input_json["_invite_request_barrier_reached"].as_boolean().is_(True),
        )
    )
    return int(session.execute(stmt).scalar_one() or 0)


def _accept_barrier_arrived_count(
    *,
    session: Session,
    barrier_key: str,
    barrier_group: str,
) -> int:
    stmt = (
        select(func.count())
        .select_from(WorkItemModel)
        .where(
            WorkItemModel.input_json["_barrier_key"].as_string() == barrier_key,
            WorkItemModel.input_json["_barrier_group"].as_string() == barrier_group,
            WorkItemModel.input_json["_accept_request_barrier_reached"].as_boolean().is_(True),
        )
    )
    return int(session.execute(stmt).scalar_one() or 0)
