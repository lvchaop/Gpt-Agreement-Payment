from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Barrier, BrokenBarrierError, Lock
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from refactor_app.application.jobs.queue import WorkQueue
from refactor_app.application.workflows.proxy import ensure_team_admin_static_proxy_url_in_session
from refactor_app.infrastructure.db.models import (
    SpaceCredentialModel,
    SpaceMembershipModel,
    SpaceModel,
    TeamAdminSessionModel,
    UserAccountModel,
)
from refactor_app.plugins.contracts import OpenAIChatGPTProvider


class SpaceMembershipInviteSyncWorkflowError(RuntimeError):
    pass


_INVITE_BARRIER_LOCK = Lock()
_INVITE_BARRIERS: dict[tuple[str, str], Barrier] = {}
SPACE_MEMBERSHIP_INVITE_WORK_COUNT = 350
SPACE_MEMBERSHIP_INVITE_BARRIER_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class SpaceMembershipInviteSyncInput:
    space_limit: int = 1
    invite_limit_per_space: int = 350
    work_count: int = SPACE_MEMBERSHIP_INVITE_WORK_COUNT
    membership_cap_per_space: int = 1000
    page_size: int = 100
    barrier_timeout_s: float = SPACE_MEMBERSHIP_INVITE_BARRIER_TIMEOUT_S


@dataclass
class SpaceMembershipInviteSyncResult:
    processed_space_count: int = 0
    synced_active_count: int = 0
    synced_invited_count: int = 0
    deleted_stale_count: int = 0
    invited_count: int = 0
    failed_invite_count: int = 0
    queued_invite_count: int = 0
    skipped_space_count: int = 0


class SpaceMembershipInviteSyncWorkflow:
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
        input_: SpaceMembershipInviteSyncInput,
        *,
        job_id: str,
        run_id: str = "",
    ) -> SpaceMembershipInviteSyncResult:
        if not job_id:
            raise SpaceMembershipInviteSyncWorkflowError("job_id is required for invite work enqueue")
        result = SpaceMembershipInviteSyncResult()
        with self._session_factory() as session:
            spaces = session.scalars(
                select(SpaceModel)
                .where(
                    SpaceModel.provider == "openai_chatgpt",
                    SpaceModel.space_type == "business",
                    SpaceModel.space_status == "active",
                )
                .order_by(SpaceModel.updated_at.asc())
                .limit(1)
            ).all()
            for space in spaces:
                result.processed_space_count += 1
                try:
                    stats = self._process_space(
                        session=session,
                        space=space,
                        input_=input_,
                        job_id=job_id,
                        run_id=run_id,
                    )
                except Exception:
                    result.skipped_space_count += 1
                    continue
                result.synced_active_count += stats["synced_active_count"]
                result.synced_invited_count += stats["synced_invited_count"]
                result.deleted_stale_count += stats["deleted_stale_count"]
                result.invited_count += stats["invited_count"]
                result.failed_invite_count += stats["failed_invite_count"]
                result.queued_invite_count += stats["queued_invite_count"]
                result.skipped_space_count += stats["skipped_space_count"]
            session.commit()
        return result

    def run_invite_work(
        self,
        *,
        space_id: str,
        user_account_id: str,
        team_admin_session_id: str,
        barrier_key: str = "",
        barrier_group: str = "",
        barrier_expected: int = 0,
        barrier_timeout_s: float = 30,
        run_id: str = "",
        work_id: str = "",
    ) -> dict:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            space = session.get(SpaceModel, space_id)
            if space is None:
                raise SpaceMembershipInviteSyncWorkflowError(f"space not found: {space_id}")
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise SpaceMembershipInviteSyncWorkflowError(
                    f"user account not found: {user_account_id}"
                )
            admin_session = session.get(TeamAdminSessionModel, team_admin_session_id)
            if admin_session is None or not admin_session.access_token:
                error = SpaceMembershipInviteSyncWorkflowError("team admin session missing access token")
                _upsert_failed_membership(
                    session=session,
                    space=space,
                    account=account,
                    error=error,
                    now=now,
                )
                session.commit()
                raise error

            access_token = admin_session.access_token
            external_space_id = space.external_space_id
            email = account.email
            cookie_header = admin_session.cookie_header
            session.commit()

        _wait_before_invite_request(
            session_factory=self._session_factory,
            barrier_key=barrier_key,
            barrier_group=barrier_group,
            expected=barrier_expected,
            timeout_s=barrier_timeout_s,
            run_id=run_id,
            work_id=work_id,
        )

        try:
            payload = self._openai_provider.invite_member(
                access_token=access_token,
                team_id=external_space_id,
                email=email,
                cookie_header=cookie_header,
                proxy_url="",
            )
        except Exception as exc:
            with self._session_factory() as session:
                space = session.get(SpaceModel, space_id)
                account = session.get(UserAccountModel, user_account_id)
                if space is not None and account is not None:
                    _upsert_failed_membership(
                        session=session,
                        space=space,
                        account=account,
                        error=exc,
                        now=datetime.now(UTC),
                    )
                    session.commit()
            raise

        with self._session_factory() as session:
            space = session.get(SpaceModel, space_id)
            account = session.get(UserAccountModel, user_account_id)
            if space is None:
                raise SpaceMembershipInviteSyncWorkflowError(f"space not found: {space_id}")
            if account is None:
                raise SpaceMembershipInviteSyncWorkflowError(
                    f"user account not found: {user_account_id}"
                )
            _upsert_invited_membership(
                session=session,
                space=space,
                account=account,
                now=datetime.now(UTC),
            )
            session.commit()
            return {
                "space_id": space.id,
                "user_account_id": account.id,
                "email": account.email,
                "invite": payload,
            }

    def sync_remote_memberships_only(self, *, space_id: str, page_size: int = 100) -> dict[str, int | str]:
        with self._session_factory() as session:
            space = session.get(SpaceModel, space_id)
            if space is None:
                raise SpaceMembershipInviteSyncWorkflowError(f"space not found: {space_id}")
            if space.space_type != "business":
                raise SpaceMembershipInviteSyncWorkflowError(
                    f"remote membership sync only supports business space: {space_id}"
                )
            stats = self._sync_remote_memberships(
                session=session,
                space=space,
                page_size=page_size,
                bind_reason="space_membership_manual_sync",
            )
            session.commit()
            return {
                "space_id": space.id,
                "external_space_id": space.external_space_id,
                **stats,
            }

    def _process_space(
        self,
        *,
        session: Session,
        space: SpaceModel,
        input_: SpaceMembershipInviteSyncInput,
        job_id: str,
        run_id: str,
    ) -> dict[str, int]:
        stats = {
            "synced_active_count": 0,
            "synced_invited_count": 0,
            "deleted_stale_count": 0,
            "invited_count": 0,
            "failed_invite_count": 0,
            "queued_invite_count": 0,
            "skipped_space_count": 0,
        }
        admin_session = _admin_session(session=session, space=space)
        if admin_session is None or not admin_session.access_token:
            stats["skipped_space_count"] = 1
            return stats

        current_count = _current_membership_count(session=session, space_id=space.id)
        remaining_capacity = max(0, int(input_.membership_cap_per_space or 1000) - current_count)
        target_count = min(max(0, int(input_.invite_limit_per_space or 350)), remaining_capacity)
        if target_count <= 0:
            return stats

        candidates = _select_invite_candidates(
            session=session,
            space_id=space.id,
            limit=target_count,
        )
        barrier_key = f"space-invite:{job_id}:{space.id}"
        worker_count = SPACE_MEMBERSHIP_INVITE_WORK_COUNT
        for index, account in enumerate(candidates):
            group_index = index // worker_count
            group_start = group_index * worker_count
            group_expected = min(worker_count, len(candidates) - group_start)
            WorkQueue(session).enqueue(
                job_id=job_id,
                work_type="space.membership_invite.account",
                input_json={
                    "space_id": space.id,
                    "user_account_id": account.id,
                    "team_admin_session_id": admin_session.id,
                    "_run_id": run_id,
                    "_barrier_key": barrier_key,
                    "_barrier_group": str(group_index),
                    "_barrier_expected": group_expected,
                    "_barrier_timeout_s": SPACE_MEMBERSHIP_INVITE_BARRIER_TIMEOUT_S,
                },
            )
            stats["queued_invite_count"] += 1
        return stats

    def _sync_remote_memberships(
        self,
        *,
        session: Session,
        space: SpaceModel,
        page_size: int,
        bind_reason: str,
    ) -> dict[str, int]:
        stats = {
            "synced_active_count": 0,
            "synced_invited_count": 0,
            "deleted_stale_count": 0,
            "skipped_space_count": 0,
        }
        admin_session = _admin_session(session=session, space=space)
        if admin_session is None or not admin_session.access_token:
            stats["skipped_space_count"] = 1
            return stats
        proxy_url = ensure_team_admin_static_proxy_url_in_session(
            session=session,
            team_admin_session_id=admin_session.id,
            bind_reason=bind_reason,
        )

        now = datetime.now(UTC)
        subscription = self._openai_provider.fetch_subscription(
            access_token=admin_session.access_token,
            account_id=space.external_space_id,
            cookie_header=admin_session.cookie_header,
            proxy_url=proxy_url,
        )
        remote_members = self._openai_provider.list_account_users(
            access_token=admin_session.access_token,
            account_id=space.external_space_id,
            cookie_header=admin_session.cookie_header,
            page_size=page_size,
            proxy_url=proxy_url,
        )
        remote_invites = self._openai_provider.list_account_invites(
            access_token=admin_session.access_token,
            account_id=space.external_space_id,
            cookie_header=admin_session.cookie_header,
            page_size=page_size,
            proxy_url=proxy_url,
        )

        _write_space_subscription_snapshot(space=space, subscription=subscription, now=now)
        account_by_email = _account_by_email(session=session)
        account_by_openai_user_id = _account_by_openai_user_id(session=session)

        seen_user_account_ids: set[str] = set()
        for member in remote_members:
            account = _match_member_account(
                member=member,
                account_by_email=account_by_email,
                account_by_openai_user_id=account_by_openai_user_id,
            )
            if account is None:
                continue
            seen_user_account_ids.add(account.id)
            _upsert_membership_from_member(
                session=session,
                space=space,
                account=account,
                member=member,
                now=now,
            )
            stats["synced_active_count"] += 1

        for invite in remote_invites:
            email = _remote_invite_email(invite).lower()
            if not email:
                continue
            account = account_by_email.get(email)
            if account is None:
                continue
            seen_user_account_ids.add(account.id)
            _upsert_membership_from_invite(
                session=session,
                space=space,
                account=account,
                now=now,
            )
            stats["synced_invited_count"] += 1

        stats["deleted_stale_count"] = _delete_stale_memberships(
            session=session,
            space=space,
            seen_user_account_ids=seen_user_account_ids,
        )
        return stats


def _admin_session(*, session: Session, space: SpaceModel) -> TeamAdminSessionModel | None:
    if space.source_admin_session_id:
        return session.get(TeamAdminSessionModel, space.source_admin_session_id)
    return session.scalars(
        select(TeamAdminSessionModel).order_by(TeamAdminSessionModel.imported_at.desc())
    ).first()


def _write_space_subscription_snapshot(
    *,
    space: SpaceModel,
    subscription: dict,
    now: datetime,
) -> None:
    seats_entitled = _safe_int(subscription.get("seats_entitled") or subscription.get("seatsEntitled"))
    seats_in_use = _safe_int(subscription.get("seats_in_use") or subscription.get("seatsInUse"))
    if seats_entitled:
        space.seats_entitled = seats_entitled
        space.seat_limit = seats_entitled
    if seats_in_use:
        space.seats_in_use = seats_in_use
    plan_type = str(subscription.get("plan_type") or subscription.get("planType") or "").strip()
    if plan_type:
        space.plan_type = plan_type
    space.raw_space_json = subscription
    space.last_subscription_sync_at = now
    space.updated_at = now


def _account_by_email(*, session: Session) -> dict[str, UserAccountModel]:
    rows = session.scalars(select(UserAccountModel).where(UserAccountModel.email != "")).all()
    return {row.email.strip().lower(): row for row in rows if row.email.strip()}


def _account_by_openai_user_id(*, session: Session) -> dict[str, UserAccountModel]:
    rows = session.scalars(
        select(UserAccountModel).where(UserAccountModel.openai_user_id != "")
    ).all()
    result: dict[str, UserAccountModel] = {}
    for row in rows:
        raw_values = _openai_user_id_candidates(row.openai_user_id)
        for value in raw_values | _stable_openai_user_ids(raw_values):
            result[value] = row
    return result


def _match_member_account(
    *,
    member: dict,
    account_by_email: dict[str, UserAccountModel],
    account_by_openai_user_id: dict[str, UserAccountModel],
) -> UserAccountModel | None:
    email = _workspace_member_email(member).lower()
    if email and email in account_by_email:
        return account_by_email[email]
    for remote_user_id in _remote_user_ids(member):
        account = account_by_openai_user_id.get(remote_user_id)
        if account is not None:
            return account
    return None


def _upsert_membership_from_member(
    *,
    session: Session,
    space: SpaceModel,
    account: UserAccountModel,
    member: dict,
    now: datetime,
) -> None:
    membership = _membership(session=session, space_id=space.id, user_account_id=account.id)
    if membership is None:
        membership = SpaceMembershipModel(
            id=f"space-membership-{uuid4()}",
            space_id=space.id,
            user_account_id=account.id,
            membership_status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(membership)
    membership.membership_status = "active"
    membership.remote_user_id = _workspace_member_user_id(member)
    membership.remote_account_user_id = str(
        member.get("account_user_id") or member.get("accountUserId") or ""
    ).strip()
    membership.remote_seat_type = str(member.get("seat_type") or "").strip()
    membership.remote_role = _workspace_member_role(member)
    membership.role = membership.remote_role
    membership.remote_synced_at = now
    membership.failure_code = ""
    membership.failure_message = ""
    membership.updated_at = now


def _upsert_membership_from_invite(
    *,
    session: Session,
    space: SpaceModel,
    account: UserAccountModel,
    now: datetime,
) -> None:
    membership = _membership(session=session, space_id=space.id, user_account_id=account.id)
    if membership is None:
        membership = SpaceMembershipModel(
            id=f"space-membership-{uuid4()}",
            space_id=space.id,
            user_account_id=account.id,
            membership_status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(membership)
    membership.membership_status = "active"
    membership.remote_synced_at = now
    membership.failure_code = ""
    membership.failure_message = ""
    membership.updated_at = now


def _delete_stale_memberships(
    *,
    session: Session,
    space: SpaceModel,
    seen_user_account_ids: set[str],
) -> int:
    rows = session.scalars(
        select(SpaceMembershipModel).where(
            SpaceMembershipModel.space_id == space.id,
            SpaceMembershipModel.membership_status.in_(("active", "invited", "accepted", "failed")),
        )
    ).all()
    deleted = 0
    for row in rows:
        if row.user_account_id in seen_user_account_ids:
            continue
        session.delete(row)
        deleted += 1
    return deleted


def _current_membership_count(*, session: Session, space_id: str) -> int:
    value = session.scalar(
        select(func.count())
        .select_from(SpaceMembershipModel)
        .where(
            SpaceMembershipModel.space_id == space_id,
            SpaceMembershipModel.membership_status.in_(("active", "invited", "accepted")),
        )
    )
    return int(value or 0)


def _select_invite_candidates(
    *,
    session: Session,
    space_id: str,
    limit: int,
) -> list[UserAccountModel]:
    existing_membership = (
        select(SpaceMembershipModel.user_account_id)
        .where(
            SpaceMembershipModel.space_id == space_id,
            SpaceMembershipModel.membership_status.in_(("active", "invited", "accepted")),
        )
        .subquery()
    )
    active_credential = (
        select(SpaceCredentialModel.user_account_id)
        .where(
            SpaceCredentialModel.space_id == space_id,
            SpaceCredentialModel.credential_status == "active",
        )
        .subquery()
    )
    return list(
        session.scalars(
            select(UserAccountModel)
            .where(
                UserAccountModel.account_status == "active",
                UserAccountModel.email != "",
                ~UserAccountModel.id.in_(select(existing_membership.c.user_account_id)),
                ~UserAccountModel.id.in_(select(active_credential.c.user_account_id)),
                UserAccountModel.session_status == "active",
                or_(
                    UserAccountModel.session_token != "",
                    UserAccountModel.cookie_header != "",
                ),
            )
            .order_by(UserAccountModel.updated_at.asc())
            .limit(max(0, int(limit or 0)))
        ).all()
    )


def _upsert_invited_membership(
    *,
    session: Session,
    space: SpaceModel,
    account: UserAccountModel,
    now: datetime,
) -> None:
    membership = _membership(session=session, space_id=space.id, user_account_id=account.id)
    if membership is None:
        membership = SpaceMembershipModel(
            id=f"space-membership-{uuid4()}",
            space_id=space.id,
            user_account_id=account.id,
            membership_status="invited",
            created_at=now,
            updated_at=now,
        )
        session.add(membership)
    membership.membership_status = "invited"
    membership.remote_synced_at = now
    membership.failure_code = ""
    membership.failure_message = ""
    membership.updated_at = now


def _upsert_failed_membership(
    *,
    session: Session,
    space: SpaceModel,
    account: UserAccountModel,
    error: Exception,
    now: datetime,
) -> None:
    membership = _membership(session=session, space_id=space.id, user_account_id=account.id)
    if membership is None:
        membership = SpaceMembershipModel(
            id=f"space-membership-{uuid4()}",
            space_id=space.id,
            user_account_id=account.id,
            membership_status="failed",
            created_at=now,
            updated_at=now,
        )
        session.add(membership)
    membership.membership_status = "failed"
    membership.failure_code = type(error).__name__[:200]
    membership.failure_message = str(error)[:1000]
    membership.updated_at = now


def _membership(
    *,
    session: Session,
    space_id: str,
    user_account_id: str,
) -> SpaceMembershipModel | None:
    return session.scalars(
        select(SpaceMembershipModel).where(
            SpaceMembershipModel.space_id == space_id,
            SpaceMembershipModel.user_account_id == user_account_id,
        )
    ).first()


def _remote_user_ids(item: dict) -> set[str]:
    values = set()
    for key in ("id", "user_id", "userId", "account_user_id", "accountUserId"):
        values.update(_openai_user_id_candidates(item.get(key)))
    user = item.get("user")
    if isinstance(user, dict):
        for key in ("id", "user_id", "userId"):
            values.update(_openai_user_id_candidates(user.get(key)))
    return _stable_openai_user_ids(values)


def _workspace_member_user_id(member: dict) -> str:
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


def _workspace_member_email(member: dict) -> str:
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


def _workspace_member_role(member: dict) -> str:
    for key in ("role", "account_user_role", "user_role"):
        text = str(member.get(key) or "").strip()
        if text:
            return text
    return ""


def _remote_invite_email(item: dict) -> str:
    for key in ("email", "email_address", "emailAddress", "recipient_email"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    user = item.get("user")
    if isinstance(user, dict):
        return str(user.get("email") or "").strip()
    return ""


def _wait_before_invite_request(
    *,
    session_factory: Callable[[], Session],
    barrier_key: str,
    barrier_group: str,
    expected: int,
    timeout_s: float,
    run_id: str,
    work_id: str,
) -> None:
    if not barrier_key or not barrier_group or expected <= 1:
        return

    key = (barrier_key, barrier_group)
    with _INVITE_BARRIER_LOCK:
        barrier = _INVITE_BARRIERS.get(key)
        if barrier is None or barrier.parties != expected or barrier.broken:
            barrier = Barrier(expected)
            _INVITE_BARRIERS[key] = barrier

    try:
        barrier.wait(timeout=timeout_s)
    except BrokenBarrierError as exc:
        with _INVITE_BARRIER_LOCK:
            if _INVITE_BARRIERS.get(key) is barrier:
                _INVITE_BARRIERS.pop(key, None)
        raise TimeoutError(
            "space invite request memory barrier timeout: "
            f"key={barrier_key} group={barrier_group} expected={expected}"
        ) from exc
    finally:
        with _INVITE_BARRIER_LOCK:
            if _INVITE_BARRIERS.get(key) is barrier and (barrier.broken or barrier.n_waiting == 0):
                _INVITE_BARRIERS.pop(key, None)


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
