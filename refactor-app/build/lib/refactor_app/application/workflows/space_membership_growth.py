from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic, sleep

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.application.jobs.queue import WorkQueue
from refactor_app.application.workflows.proxy import ensure_team_admin_static_proxy_url_in_session
from refactor_app.application.workflows.space_membership_invite_sync import (
    SpaceMembershipInviteSyncWorkflow,
    _admin_session,
    _invite_response_items_by_email,
    _openai_user_id_candidates,
    _remote_invite_email,
    _remote_user_ids,
    _select_invite_candidates,
    _upsert_invited_membership,
    _workspace_member_email,
)
from refactor_app.infrastructure.db.models import (
    JobModel,
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
    WorkItemModel,
)
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.contracts import OpenAIChatGPTProvider
from refactor_app.plugins.openai_chatgpt.client import OpenAIChatGPTTimeoutError

MAX_GROWTH_INVITES = 16
TARGET_GROWTH_MEMBERS = 999
DEFAULT_SESSION_WORK_COUNT = 16
DEFAULT_SESSION_WAIT_TIMEOUT_S = 900
SESSION_WAIT_POLL_S = 0.5
INVITE_TIMEOUT_SYNC_DELAY_S = 30

_TERMINAL_WORK_STATUSES = {"succeeded", "skipped", "failed", "cancelled"}


class SpaceMembershipGrowthError(RuntimeError):
    pass


@dataclass(frozen=True)
class _RemoteContext:
    space_id: str
    external_space_id: str
    admin_session_id: str
    access_token: str
    cookie_header: str
    proxy_url: str


def growth_invite_count(
    *,
    seats_entitled: int,
    seats_in_use: int,
    available_account_count: int,
    max_invites: int = MAX_GROWTH_INVITES,
    target_members: int = TARGET_GROWTH_MEMBERS,
) -> int:
    if seats_entitled < 1:
        raise SpaceMembershipGrowthError("remote subscription has no valid seats_entitled")
    if seats_in_use < 0:
        raise SpaceMembershipGrowthError("remote subscription has invalid seats_in_use")
    desired = max(0, (2 * seats_entitled) - seats_in_use)
    remaining_to_target = max(0, target_members - seats_in_use)
    return min(
        max(0, int(max_invites)),
        desired,
        remaining_to_target,
        max(0, int(available_account_count)),
    )


class SpaceMembershipGrowthWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
        sleep_fn: Callable[[float], None] = sleep,
        monotonic_fn: Callable[[], float] = monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn

    def run_invite_batch_work(
        self,
        *,
        job_id: str,
        run_id: str,
        space_id: str,
        session_wait_timeout_s: int = DEFAULT_SESSION_WAIT_TIMEOUT_S,
    ) -> dict:
        if not job_id:
            raise SpaceMembershipGrowthError("job_id is required")
        context = self._remote_context(
            space_id=space_id,
            bind_reason="space_membership_growth_invite",
        )
        subscription = self._openai_provider.fetch_subscription(
            access_token=context.access_token,
            account_id=context.external_space_id,
            cookie_header=context.cookie_header,
            proxy_url=context.proxy_url,
        )
        seats_entitled = _required_non_negative_int(
            subscription,
            "seats_entitled",
            minimum=1,
        )
        seats_in_use = _required_non_negative_int(subscription, "seats_in_use", minimum=0)
        remote_members = self._openai_provider.list_account_users(
            access_token=context.access_token,
            account_id=context.external_space_id,
            cookie_header=context.cookie_header,
            page_size=100,
            proxy_url=context.proxy_url,
        )
        remote_invites = self._openai_provider.list_account_invites(
            access_token=context.access_token,
            account_id=context.external_space_id,
            cookie_header=context.cookie_header,
            page_size=100,
            proxy_url=context.proxy_url,
        )
        excluded_emails = {
            email.lower()
            for email in (
                *(_workspace_member_email(item) for item in remote_members),
                *(_remote_invite_email(item) for item in remote_invites),
            )
            if email
        }

        with self._session_factory() as session:
            space = _active_business_space(session=session, space_id=space_id)
            _write_remote_subscription(
                space=space,
                subscription=subscription,
                seats_entitled=seats_entitled,
                seats_in_use=seats_in_use,
            )
            candidates = _select_invite_candidates(
                session=session,
                space_id=space.id,
                limit=MAX_GROWTH_INVITES,
                excluded_emails=excluded_emails,
            )
            invite_count = growth_invite_count(
                seats_entitled=seats_entitled,
                seats_in_use=seats_in_use,
                available_account_count=len(candidates),
            )
            selected = candidates[:invite_count]
            session.commit()

        self._write_event(
            run_id=run_id,
            event_type="space_growth.invite_planned",
            message="space membership growth invite batch planned",
            data_json={
                "space_id": space_id,
                "external_space_id": context.external_space_id,
                "seats_entitled": seats_entitled,
                "seats_in_use": seats_in_use,
                "selected_count": len(selected),
            },
        )
        if not selected:
            return {
                "_work_outcome": "skipped",
                "skip_reason": "growth invite calculation selected no account",
                "space_id": space_id,
                "seats_entitled": seats_entitled,
                "seats_in_use": seats_in_use,
                "selected_count": 0,
            }

        requested_emails = [account.email for account in selected]
        try:
            payload = self._openai_provider.invite_members(
                access_token=context.access_token,
                team_id=context.external_space_id,
                emails=requested_emails,
                cookie_header=context.cookie_header,
                proxy_url=context.proxy_url,
            )
            successful_by_email = _invite_response_items_by_email(payload.get("account_invites"))
            failed_by_email = _invite_response_items_by_email(payload.get("errored_emails"))
            successful_emails = set(successful_by_email) - set(failed_by_email)
            timed_out = False
        except OpenAIChatGPTTimeoutError:
            timed_out = True
            self._sleep(INVITE_TIMEOUT_SYNC_DELAY_S)
            successful_emails = self._remote_requested_emails(
                context=context,
                requested_emails=requested_emails,
            )
            failed_by_email = {}

        selected_by_email = {account.email.strip().lower(): account for account in selected}
        successful_accounts = [
            selected_by_email[email]
            for email in sorted(successful_emails)
            if email in selected_by_email
        ]
        failed_count = len(selected) - len(successful_accounts)
        if not successful_accounts:
            raise SpaceMembershipGrowthError(
                "growth batch invite produced no successful email: "
                f"requested={len(selected)} failed={failed_count} timed_out={timed_out}"
            )

        now = datetime.now(UTC)
        with self._session_factory() as session:
            space = _active_business_space(session=session, space_id=space_id)
            accounts = session.scalars(
                select(UserAccountModel).where(
                    UserAccountModel.id.in_([account.id for account in successful_accounts])
                )
            ).all()
            account_by_id = {account.id: account for account in accounts}
            ordered_accounts = [
                account_by_id[account.id]
                for account in successful_accounts
                if account.id in account_by_id
            ]
            if len(ordered_accounts) != len(successful_accounts):
                raise SpaceMembershipGrowthError(
                    "invited user account disappeared before work enqueue"
                )
            queue = WorkQueue(session)
            session_works: list[WorkItemModel] = []
            for account in ordered_accounts:
                _upsert_invited_membership(
                    session=session,
                    space=space,
                    account=account,
                    now=now,
                )
                session_works.append(
                    queue.enqueue(
                        job_id=job_id,
                        work_type="space.membership_growth.session",
                        priority=1,
                        input_json={
                            "space_id": space.id,
                            "user_account_id": account.id,
                            "_run_id": run_id,
                        },
                    )
                )
            session.flush()
            final_work = queue.enqueue(
                job_id=job_id,
                work_type="space.membership_growth.finalize",
                priority=0,
                execution_key=f"space-membership-growth-finalize:{space.external_space_id}",
                input_json={
                    "job_id": job_id,
                    "space_id": space.id,
                    "user_account_ids": [account.id for account in ordered_accounts],
                    "session_work_ids": [work.id for work in session_works],
                    "session_wait_timeout_s": max(1, int(session_wait_timeout_s)),
                    "_run_id": run_id,
                },
            )
            session.commit()

        self._write_event(
            run_id=run_id,
            event_type="space_growth.session_works_queued",
            message="invited accounts queued for session refresh",
            data_json={
                "space_id": space_id,
                "requested_count": len(selected),
                "invite_succeeded_count": len(successful_accounts),
                "invite_failed_count": failed_count,
                "session_work_count": len(session_works),
                "final_work_id": final_work.id,
                "invite_timed_out": timed_out,
            },
        )
        return {
            "space_id": space_id,
            "seats_entitled": seats_entitled,
            "seats_in_use": seats_in_use,
            "requested_count": len(selected),
            "invite_succeeded_count": len(successful_accounts),
            "invite_failed_count": failed_count,
            "session_work_count": len(session_works),
            "final_work_id": final_work.id,
            "invite_timed_out": timed_out,
        }

    def run_finalize_work(
        self,
        *,
        job_id: str,
        run_id: str,
        space_id: str,
        user_account_ids: list[str],
        session_work_ids: list[str],
        session_wait_timeout_s: int,
    ) -> dict:
        session_summary = self._wait_for_session_works(
            job_id=job_id,
            work_ids=session_work_ids,
            timeout_s=session_wait_timeout_s,
        )
        context = self._remote_context(
            space_id=space_id,
            bind_reason="space_membership_growth_finalize",
        )
        remote_members = self._openai_provider.list_account_users(
            access_token=context.access_token,
            account_id=context.external_space_id,
            cookie_header=context.cookie_header,
            page_size=100,
            proxy_url=context.proxy_url,
        )
        confirmed = self._confirmed_members(
            space_id=space_id,
            user_account_ids=user_account_ids,
            remote_members=remote_members,
        )
        self._write_event(
            run_id=run_id,
            event_type="space_growth.remote_members_checked",
            message="session results reconciled against remote workspace users",
            data_json={
                "space_id": space_id,
                "session_work_summary": session_summary,
                "remote_member_count": len(remote_members),
                "confirmed_joined_count": len(confirmed),
            },
        )
        if not confirmed:
            self._sync_local(space_id=space_id)
            raise SpaceMembershipGrowthError(
                "no invited account was confirmed by remote workspace users"
            )

        removable = [item for item in confirmed if _remote_member_delete_id(item[1])]
        if not removable:
            raise SpaceMembershipGrowthError("confirmed remote members have no removable user id")
        account, member = sorted(removable, key=lambda item: item[0].id)[0]
        remote_user_id = _remote_member_delete_id(member)
        delete_timed_out = False
        try:
            self._openai_provider.remove_account_user(
                access_token=context.access_token,
                account_id=context.external_space_id,
                user_id=remote_user_id,
                cookie_header=context.cookie_header,
                proxy_url=context.proxy_url,
            )
        except OpenAIChatGPTTimeoutError:
            delete_timed_out = True

        remote_after = self._openai_provider.list_account_users(
            access_token=context.access_token,
            account_id=context.external_space_id,
            cookie_header=context.cookie_header,
            page_size=100,
            proxy_url=context.proxy_url,
        )
        if _remote_member_present(
            members=remote_after,
            email=account.email,
            remote_user_id=remote_user_id,
        ):
            if delete_timed_out:
                raise SpaceMembershipGrowthError(
                    "member removal timed out and remote user is still present"
                )
            raise SpaceMembershipGrowthError(
                "member removal response succeeded but user is still present"
            )

        sync_result = self._sync_local(space_id=space_id)
        self._write_event(
            run_id=run_id,
            event_type="space_growth.member_removed",
            message="one confirmed joined member removed; growth round completed",
            data_json={
                "space_id": space_id,
                "user_account_id": account.id,
                "email": account.email,
                "remote_user_id": remote_user_id,
                "confirmed_joined_count": len(confirmed),
                "remote_member_count_after": len(remote_after),
                "delete_timed_out": delete_timed_out,
                "sync_result": sync_result,
            },
        )
        return {
            "space_id": space_id,
            "confirmed_joined_count": len(confirmed),
            "removed_user_account_id": account.id,
            "removed_email": account.email,
            "removed_remote_user_id": remote_user_id,
            "remote_member_count_before": len(remote_members),
            "remote_member_count_after": len(remote_after),
            "delete_timed_out": delete_timed_out,
            "session_work_summary": session_summary,
            "sync_result": sync_result,
        }

    def _remote_context(self, *, space_id: str, bind_reason: str) -> _RemoteContext:
        with self._session_factory() as session:
            space = _active_business_space(session=session, space_id=space_id)
            admin = _admin_session(session=session, space=space)
            if admin is None or not admin.access_token:
                raise SpaceMembershipGrowthError("team admin session missing access token")
            proxy_url = ensure_team_admin_static_proxy_url_in_session(
                session=session,
                team_admin_session_id=admin.id,
                bind_reason=bind_reason,
            )
            context = _RemoteContext(
                space_id=space.id,
                external_space_id=space.external_space_id,
                admin_session_id=admin.id,
                access_token=admin.access_token,
                cookie_header=admin.cookie_header,
                proxy_url=proxy_url,
            )
            session.commit()
            return context

    def _remote_requested_emails(
        self,
        *,
        context: _RemoteContext,
        requested_emails: list[str],
    ) -> set[str]:
        remote_members = self._openai_provider.list_account_users(
            access_token=context.access_token,
            account_id=context.external_space_id,
            cookie_header=context.cookie_header,
            page_size=100,
            proxy_url=context.proxy_url,
        )
        remote_invites = self._openai_provider.list_account_invites(
            access_token=context.access_token,
            account_id=context.external_space_id,
            cookie_header=context.cookie_header,
            page_size=100,
            proxy_url=context.proxy_url,
        )
        remote_emails = {
            email.lower()
            for email in (
                *(_workspace_member_email(item) for item in remote_members),
                *(_remote_invite_email(item) for item in remote_invites),
            )
            if email
        }
        return {email.strip().lower() for email in requested_emails} & remote_emails

    def _wait_for_session_works(
        self,
        *,
        job_id: str,
        work_ids: list[str],
        timeout_s: int,
    ) -> dict[str, int]:
        unique_ids = list(dict.fromkeys(str(item) for item in work_ids if str(item)))
        if not unique_ids:
            raise SpaceMembershipGrowthError("finalize work has no session works")
        deadline = self._monotonic() + max(1, int(timeout_s))
        while True:
            with self._session_factory() as session:
                job = session.get(JobModel, job_id)
                if job is None:
                    raise SpaceMembershipGrowthError("growth job disappeared")
                if job.job_status == "cancelled":
                    raise SpaceMembershipGrowthError("growth job cancelled")
                rows = session.execute(
                    select(WorkItemModel.id, WorkItemModel.work_status).where(
                        WorkItemModel.id.in_(unique_ids)
                    )
                ).all()
            if len(rows) != len(unique_ids):
                raise SpaceMembershipGrowthError("one or more session works disappeared")
            if all(status in _TERMINAL_WORK_STATUSES for _, status in rows):
                summary = {status: 0 for status in _TERMINAL_WORK_STATUSES}
                for _, status in rows:
                    summary[status] += 1
                return summary
            if self._monotonic() >= deadline:
                raise SpaceMembershipGrowthError(
                    f"session works did not finish within {max(1, int(timeout_s))}s"
                )
            self._sleep(SESSION_WAIT_POLL_S)

    def _confirmed_members(
        self,
        *,
        space_id: str,
        user_account_ids: list[str],
        remote_members: list[dict],
    ) -> list[tuple[UserAccountModel, dict]]:
        requested_ids = list(dict.fromkeys(str(item) for item in user_account_ids if str(item)))
        with self._session_factory() as session:
            accounts = session.scalars(
                select(UserAccountModel).where(UserAccountModel.id.in_(requested_ids))
            ).all()
            memberships = session.scalars(
                select(SpaceMembershipModel).where(
                    SpaceMembershipModel.space_id == space_id,
                    SpaceMembershipModel.user_account_id.in_(requested_ids),
                )
            ).all()
        membership_by_account = {row.user_account_id: row for row in memberships}
        identities: dict[str, tuple[str, set[str]]] = {}
        for account in accounts:
            membership = membership_by_account.get(account.id)
            remote_ids = _openai_user_id_candidates(account.openai_user_id)
            if membership is not None:
                remote_ids.update(_openai_user_id_candidates(membership.remote_user_id))
                remote_ids.update(_openai_user_id_candidates(membership.remote_account_user_id))
            identities[account.id] = (account.email.strip().lower(), remote_ids)

        confirmed: list[tuple[UserAccountModel, dict]] = []
        matched_account_ids: set[str] = set()
        for member in remote_members:
            member_email = _workspace_member_email(member).lower()
            member_ids = _remote_user_ids(member)
            for account in accounts:
                if account.id in matched_account_ids:
                    continue
                account_email, account_remote_ids = identities[account.id]
                if (member_email and member_email == account_email) or (
                    member_ids
                    and account_remote_ids
                    and member_ids.intersection(account_remote_ids)
                ):
                    confirmed.append((account, member))
                    matched_account_ids.add(account.id)
                    break
        return confirmed

    def _sync_local(self, *, space_id: str) -> dict[str, int | str]:
        return SpaceMembershipInviteSyncWorkflow(
            session_factory=self._session_factory,
            openai_provider=self._openai_provider,
        ).sync_remote_memberships_only(space_id=space_id, page_size=100)

    def _write_event(
        self,
        *,
        run_id: str,
        event_type: str,
        message: str,
        data_json: dict,
    ) -> None:
        if not run_id:
            return
        with self._session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type=event_type,
                message=message,
                data_json=data_json,
            )
            session.commit()


def _active_business_space(*, session: Session, space_id: str) -> SpaceModel:
    space = session.get(SpaceModel, space_id)
    if space is None:
        raise SpaceMembershipGrowthError(f"space not found: {space_id}")
    if space.space_type != "business":
        raise SpaceMembershipGrowthError("membership growth only supports business spaces")
    if space.space_status != "active":
        raise SpaceMembershipGrowthError("space is not active")
    if not space.external_space_id:
        raise SpaceMembershipGrowthError("space has no external space id")
    return space


def _write_remote_subscription(
    *,
    space: SpaceModel,
    subscription: dict,
    seats_entitled: int,
    seats_in_use: int,
) -> None:
    now = datetime.now(UTC)
    space.seats_entitled = seats_entitled
    space.seat_limit = seats_entitled
    space.seats_in_use = seats_in_use
    plan_type = str(subscription.get("plan_type") or subscription.get("planType") or "").strip()
    if plan_type:
        space.plan_type = plan_type
    space.raw_space_json = subscription
    space.last_subscription_sync_at = now
    space.updated_at = now


def _required_non_negative_int(payload: dict, key: str, *, minimum: int) -> int:
    value = payload.get(key)
    if value is None:
        camel_key = "".join(
            part if index == 0 else part.capitalize() for index, part in enumerate(key.split("_"))
        )
        value = payload.get(camel_key)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SpaceMembershipGrowthError(f"remote subscription missing valid {key}") from exc
    if parsed < minimum:
        raise SpaceMembershipGrowthError(f"remote subscription has invalid {key}: {parsed}")
    return parsed


def _remote_member_delete_id(member: dict) -> str:
    user = member.get("user")
    for value in (
        member.get("user_id"),
        member.get("id"),
        member.get("account_user_id"),
        member.get("accountUserId"),
        user.get("id") if isinstance(user, dict) else "",
        user.get("user_id") if isinstance(user, dict) else "",
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _remote_member_present(
    *,
    members: list[dict],
    email: str,
    remote_user_id: str,
) -> bool:
    target_email = email.strip().lower()
    target_ids = _openai_user_id_candidates(remote_user_id)
    for member in members:
        if target_email and _workspace_member_email(member).lower() == target_email:
            return True
        if target_ids.intersection(_remote_user_ids(member)):
            return True
        if _remote_member_delete_id(member) == remote_user_id:
            return True
    return False
