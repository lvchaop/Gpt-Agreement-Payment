from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import sleep
from typing import Protocol

from invite_executor.proxy_pool import StaticProxyAssignment
from invite_executor.replenishment_models import (
    AccountDeactivatedProvisioningError,
    AuthorizationForbiddenProvisioningError,
    ChatGPTAccountMissingProvisioningError,
    ProvisionedCodexCredential,
    RemoteMember,
    SelectChannelProvisioningError,
    SpaceAdminContext,
    SpaceCycleResult,
    SpaceRemoteSnapshot,
    SpaceReplenishmentConfig,
)
from invite_executor.sub2api import (
    Sub2APIAccount,
    accounts_for_space,
    build_sub2api_codex_payload,
    resolve_usage_signal,
    sub2api_idempotency_key,
)


class SpaceGateway(Protocol):
    def snapshot(self, space: SpaceReplenishmentConfig) -> SpaceRemoteSnapshot: ...

    def list_members(
        self,
        space: SpaceReplenishmentConfig,
        admin: SpaceAdminContext,
    ) -> tuple[RemoteMember, ...]: ...

    def remove_member(
        self,
        space: SpaceReplenishmentConfig,
        admin: SpaceAdminContext,
        *,
        user_id: str,
    ) -> None: ...

    def revoke_invite(
        self,
        space: SpaceReplenishmentConfig,
        admin: SpaceAdminContext,
        *,
        email: str,
    ) -> None: ...

    def account_proxy(self, email: str) -> StaticProxyAssignment: ...


class CredentialProvisioner(Protocol):
    def provision(
        self,
        *,
        space: SpaceReplenishmentConfig,
        email: str,
        proxy_assignment: StaticProxyAssignment,
    ) -> ProvisionedCodexCredential: ...

    def reauthorize(
        self,
        *,
        space: SpaceReplenishmentConfig,
        email: str,
        proxy_assignment: StaticProxyAssignment,
    ) -> ProvisionedCodexCredential: ...


class DownstreamAccountClient(Protocol):
    def list_openai_accounts(self, *, group_id: int) -> list[Sub2APIAccount]: ...

    def push_codex_credential(
        self,
        *,
        payload: object,
        group_ids: tuple[int, ...],
        idempotency_key: str,
    ) -> None: ...

    def apply_codex_credential(
        self,
        *,
        account_id: int,
        payload: object,
        idempotency_key: str,
    ) -> Sub2APIAccount: ...

    def delete_account(self, account_id: int) -> None: ...


class SpaceReplenishmentEngine:
    def __init__(
        self,
        *,
        gateway: SpaceGateway,
        provisioner: CredentialProvisioner,
        downstream: DownstreamAccountClient,
        downstream_group_id: int,
        downstream_push_group_ids: tuple[int, ...] | None = None,
        usage_threshold_percent: float = 90.0,
        usage_stale_after_s: int = 7200,
        member_confirm_attempts: int = 3,
        member_confirm_interval_s: float = 2.0,
        candidate_failure_cooldown_s: int = 600,
        now_fn: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[float], None] = sleep,
    ) -> None:
        if int(downstream_group_id) <= 0:
            raise ValueError("downstream_group_id must be positive")
        if float(usage_threshold_percent) <= 0:
            raise ValueError("usage_threshold_percent must be positive")
        self._gateway = gateway
        self._provisioner = provisioner
        self._downstream = downstream
        self._downstream_group_id = int(downstream_group_id)
        push_group_ids = downstream_push_group_ids or (self._downstream_group_id,)
        normalized_push_group_ids = tuple(
            dict.fromkeys(int(group_id) for group_id in push_group_ids if int(group_id) > 0)
        )
        if not normalized_push_group_ids:
            raise ValueError("downstream_push_group_ids must contain a positive group ID")
        if self._downstream_group_id not in normalized_push_group_ids:
            normalized_push_group_ids = (
                self._downstream_group_id,
                *normalized_push_group_ids,
            )
        self._downstream_push_group_ids = normalized_push_group_ids
        self._usage_threshold_percent = float(usage_threshold_percent)
        self._usage_stale_after_s = max(1, int(usage_stale_after_s))
        self._member_confirm_attempts = max(1, int(member_confirm_attempts))
        self._member_confirm_interval_s = max(0.0, float(member_confirm_interval_s))
        self._candidate_failure_cooldown_s = max(0, int(candidate_failure_cooldown_s))
        self._now_fn = now_fn or (lambda: datetime.now(UTC))
        self._sleep = sleep_fn
        self._cooldown_lock = Lock()
        self._candidate_cooldowns: dict[tuple[str, str], datetime] = {}

    def prepare(self) -> None:
        prepare = getattr(self._provisioner, "prepare", None)
        if not callable(prepare):
            return
        prepare()

    def close(self) -> None:
        for component in (self._provisioner, self._downstream):
            close = getattr(component, "close", None)
            if callable(close):
                close()

    def run(self, space: SpaceReplenishmentConfig) -> SpaceCycleResult:
        started_at = self._now()
        context: dict[str, object] = {
            "member_count": 0,
            "non_admin_member_count": 0,
            "invite_count": 0,
            "downstream_account_count": 0,
            "seat_limit": 0,
            "new_email": "",
            "new_chatgpt_user_id": "",
            "replaced_chatgpt_user_id": "",
            "downstream_account_id": 0,
            "removed_downstream_account_id": 0,
        }
        try:
            status, action, reason = self._run_cycle(space, context)
            return SpaceCycleResult(
                external_space_id=space.external_space_id,
                status=status,
                action=action,
                reason=reason,
                started_at=started_at,
                finished_at=self._now(),
                **{key: value for key, value in context.items() if not key.startswith("_")},
            )
        except Exception as exc:
            email = str(context.get("new_email") or "")
            if email:
                self._mark_candidate_cooldown(space.external_space_id, email)
            return SpaceCycleResult(
                external_space_id=space.external_space_id,
                status="failed",
                action=str(context.get("_action") or "cycle"),
                reason="cycle_failed",
                error_type=type(exc).__name__,
                error_message=str(exc)[:1000],
                started_at=started_at,
                finished_at=self._now(),
                **{key: value for key, value in context.items() if not key.startswith("_")},
            )

    def _run_cycle(
        self,
        space: SpaceReplenishmentConfig,
        context: dict[str, object],
    ) -> tuple[str, str, str]:
        snapshot = self._gateway.snapshot(space)
        downstream_accounts = accounts_for_space(
            self._downstream.list_openai_accounts(group_id=self._downstream_group_id),
            external_space_id=space.external_space_id,
        )
        admin_user_ids = _admin_user_ids(snapshot)
        if not admin_user_ids:
            context.update(
                member_count=len(snapshot.members),
                non_admin_member_count=0,
                invite_count=len(snapshot.invites),
                downstream_account_count=0,
            )
            return "waiting", "none", "remote_admin_not_identified"
        non_admin_members = _non_admin_members(snapshot, admin_user_ids)
        non_admin_user_ids = {member.user_id for member in non_admin_members}
        member_accounts = [
            account
            for account in downstream_accounts
            if account.chatgpt_user_id in non_admin_user_ids
        ]
        context.update(
            member_count=len(snapshot.members),
            non_admin_member_count=len(non_admin_members),
            invite_count=len(snapshot.invites),
            downstream_account_count=len(member_accounts),
            seat_limit=snapshot.seat_limit,
        )

        recovery = self._recover_pushed_replacement(
            space=space,
            snapshot=snapshot,
            downstream_accounts=downstream_accounts,
            admin_user_ids=admin_user_ids,
            context=context,
        )
        if recovery is not None:
            return recovery

        unpublished_members = [
            member
            for member in non_admin_members
            if _account_by_user_id(member_accounts, member.user_id) is None
        ]
        unpublished_member = next(
            (
                member
                for member in unpublished_members
                if member.email and "@" in member.email
                and not self._candidate_in_cooldown(
                    space.external_space_id,
                    member.email,
                )
            ),
            None,
        )
        unpublished_member_with_email = any(
            member.email and "@" in member.email for member in unpublished_members
        )

        replacement: Sub2APIAccount | None = None
        replacement_reason = ""
        recovery_reason = ""
        expected_user_id = ""
        if unpublished_member is not None:
            candidate_email = unpublished_member.email.strip()
            expected_user_id = unpublished_member.user_id
            context["_action"] = "push_existing"
        elif unpublished_member_with_email:
            return "waiting", "push_existing", "remote_member_candidate_cooldown"
        elif unpublished_members:
            return "waiting", "push_existing", "remote_member_email_missing"
        else:
            replacement = self._replacement_target(
                space=space,
                member_accounts=member_accounts,
            )
            if replacement is None:
                if len(non_admin_members) >= snapshot.seat_limit:
                    return "skipped", "none", "space_capacity_healthy"
                context["_action"] = "provision"
            else:
                if (
                    replacement.status.strip().casefold() == "error"
                    and replacement.error_http_status == 401
                ):
                    context["_action"] = "reauthorize"
                    context["new_email"] = replacement.email
                    context["replaced_chatgpt_user_id"] = replacement.chatgpt_user_id
                    try:
                        return self._reauthorize_401_account(
                            space=space,
                            snapshot=snapshot,
                            account=replacement,
                            context=context,
                        )
                    except AuthorizationForbiddenProvisioningError:
                        self._mark_candidate_cooldown(
                            space.external_space_id,
                            replacement.email,
                        )
                        replacement_reason = (
                            "downstream_account_401_reauthorization_forbidden"
                        )
                else:
                    replacement_reason = (
                        "downstream_account_error"
                        if replacement.status.strip().casefold() == "error"
                        else "usage_threshold_reached"
                    )
                context["_action"] = "replace"
                context["replaced_chatgpt_user_id"] = replacement.chatgpt_user_id
                if not self._remove_remote_member_and_confirm(
                    space=space,
                    snapshot=snapshot,
                    user_id=replacement.chatgpt_user_id,
                ):
                    return "waiting", "replace", "old_remote_member_still_present"
                self._downstream.delete_account(replacement.id)
                context["removed_downstream_account_id"] = replacement.id
                downstream_accounts = [
                    account for account in downstream_accounts if account.id != replacement.id
                ]
                snapshot = self._gateway.snapshot(space)
                admin_user_ids = _admin_user_ids(snapshot)
                non_admin_members = _non_admin_members(snapshot, admin_user_ids)
                context.update(
                    member_count=len(snapshot.members),
                    non_admin_member_count=len(non_admin_members),
                    invite_count=len(snapshot.invites),
                    seat_limit=snapshot.seat_limit,
                )

            candidate_email = self._select_invite_email(
                space=space,
                snapshot=snapshot,
            )
            if not candidate_email:
                return "waiting", str(context["_action"]), "no_pending_invite_candidate"
        context["new_email"] = candidate_email

        attempted_emails: set[str] = set()
        while True:
            attempted_emails.add(candidate_email.casefold())
            try:
                credential = self._provision_credential(
                    space=space,
                    email=candidate_email,
                    proxy_assignment=self._gateway.account_proxy(candidate_email),
                    reauthorize=bool(expected_user_id),
                )
                break
            except (
                AccountDeactivatedProvisioningError,
                ChatGPTAccountMissingProvisioningError,
                SelectChannelProvisioningError,
            ) as exc:
                failure_snapshot = self._gateway.snapshot(space)
                failed_user_id = expected_user_id
                if isinstance(exc, SelectChannelProvisioningError):
                    failed_user_id = exc.chatgpt_user_id or failed_user_id
                    failure_code = "select_channel"
                elif isinstance(exc, ChatGPTAccountMissingProvisioningError):
                    failure_code = "account_missing"
                else:
                    failure_code = "deactivated"
                if not failed_user_id:
                    failed_member = _member_by_email(
                        failure_snapshot.members,
                        candidate_email,
                    )
                    failed_user_id = failed_member.user_id if failed_member is not None else ""
                recovery_target = "member_removed"
                if failed_user_id:
                    if not self._remove_remote_member_and_confirm(
                        space=space,
                        snapshot=failure_snapshot,
                        user_id=failed_user_id,
                    ):
                        return (
                            "waiting",
                            f"replace_{failure_code}",
                            f"{failure_code}_remote_member_still_present",
                        )
                elif isinstance(
                    exc,
                    (
                        AccountDeactivatedProvisioningError,
                        ChatGPTAccountMissingProvisioningError,
                    ),
                ):
                    if not self._remove_remote_invite_and_confirm(
                        space=space,
                        snapshot=failure_snapshot,
                        email=candidate_email,
                    ):
                        return (
                            "waiting",
                            f"replace_{failure_code}",
                            f"{failure_code}_remote_invite_still_present",
                        )
                    recovery_target = "invite_revoked"
                failed_account = _account_by_user_id(downstream_accounts, failed_user_id)
                if failed_account is not None:
                    self._downstream.delete_account(failed_account.id)
                    context["removed_downstream_account_id"] = failed_account.id
                    downstream_accounts = [
                        account
                        for account in downstream_accounts
                        if account.id != failed_account.id
                    ]
                self._mark_candidate_cooldown(space.external_space_id, candidate_email)
                recovery_reason = f"{failure_code}_{recovery_target}_and_replenished"
                if not context.get("replaced_chatgpt_user_id") and failed_user_id:
                    context["replaced_chatgpt_user_id"] = failed_user_id
                if replacement is None:
                    context["_action"] = f"replace_{failure_code}"
                expected_user_id = ""
                snapshot = self._gateway.snapshot(space)
                context.update(
                    member_count=len(snapshot.members),
                    non_admin_member_count=len(
                        _non_admin_members(snapshot, _admin_user_ids(snapshot))
                    ),
                    invite_count=len(snapshot.invites),
                    seat_limit=snapshot.seat_limit,
                )
                candidate_email = self._select_invite_email(
                    space=space,
                    snapshot=snapshot,
                    excluded_emails=attempted_emails,
                )
                if not candidate_email:
                    context["new_email"] = ""
                    return (
                        "waiting",
                        str(context["_action"]),
                        f"{failure_code}_{recovery_target}_no_pending_invite",
                    )
                context["new_email"] = candidate_email
        if credential.external_space_id != space.external_space_id:
            raise RuntimeError(
                "provisioned credential belongs to another space: "
                f"expected={space.external_space_id} actual={credential.external_space_id}"
            )
        if not credential.chatgpt_user_id:
            raise RuntimeError("provisioned credential has no chatgpt_user_id")
        if expected_user_id and credential.chatgpt_user_id != expected_user_id:
            raise RuntimeError(
                "provisioned credential does not belong to the existing remote member: "
                f"expected={expected_user_id} actual={credential.chatgpt_user_id}"
            )
        context["new_chatgpt_user_id"] = credential.chatgpt_user_id

        confirmed_members = self._wait_for_member(
            space=space,
            admin=snapshot.admin,
            user_id=credential.chatgpt_user_id,
        )
        if not _member_present(confirmed_members, credential.chatgpt_user_id):
            raise RuntimeError(
                "new account is not present in the target space remote users response: "
                f"user_id={credential.chatgpt_user_id}"
            )

        current_accounts = accounts_for_space(
            self._downstream.list_openai_accounts(group_id=self._downstream_group_id),
            external_space_id=space.external_space_id,
        )
        created = _account_by_user_id(current_accounts, credential.chatgpt_user_id)
        if created is None:
            payload = build_sub2api_codex_payload(
                space=space,
                credential=credential,
            )
            self._downstream.push_codex_credential(
                payload=payload,
                group_ids=self._downstream_push_group_ids,
                idempotency_key=sub2api_idempotency_key(
                    space_id=space.external_space_id,
                    chatgpt_user_id=credential.chatgpt_user_id,
                    access_token=credential.access_token,
                ),
            )
            current_accounts = accounts_for_space(
                self._downstream.list_openai_accounts(group_id=self._downstream_group_id),
                external_space_id=space.external_space_id,
            )
            created = _account_by_user_id(current_accounts, credential.chatgpt_user_id)
            if created is None:
                raise RuntimeError(
                    "Sub2API import completed but the account was not found: "
                    f"user_id={credential.chatgpt_user_id}"
                )
        context["downstream_account_id"] = created.id

        if replacement is not None:
            return "succeeded", "replace", f"replacement_completed:{replacement_reason}"
        if recovery_reason:
            return "succeeded", str(context["_action"]), recovery_reason
        if expected_user_id:
            return "succeeded", "push_existing", "existing_member_credential_pushed"
        return "succeeded", "provision", "credential_pushed"

    def _provision_credential(
        self,
        *,
        space: SpaceReplenishmentConfig,
        email: str,
        proxy_assignment: StaticProxyAssignment,
        reauthorize: bool = False,
    ) -> ProvisionedCodexCredential:
        method = (
            self._provisioner.reauthorize if reauthorize else self._provisioner.provision
        )
        return method(
            space=space,
            email=email,
            proxy_assignment=proxy_assignment,
        )

    def _reauthorize_401_account(
        self,
        *,
        space: SpaceReplenishmentConfig,
        snapshot: SpaceRemoteSnapshot,
        account: Sub2APIAccount,
        context: dict[str, object],
    ) -> tuple[str, str, str]:
        email = account.email.strip()
        if not email or "@" not in email:
            raise RuntimeError(
                "Sub2API 401 account is missing an email for reauthorization: "
                f"account_id={account.id}"
            )
        credential = self._provision_credential(
            space=space,
            email=email,
            proxy_assignment=self._gateway.account_proxy(email),
            reauthorize=True,
        )
        if credential.external_space_id != space.external_space_id:
            raise RuntimeError(
                "reauthorized credential belongs to another space: "
                f"expected={space.external_space_id} "
                f"actual={credential.external_space_id}"
            )
        if credential.chatgpt_user_id != account.chatgpt_user_id:
            raise RuntimeError(
                "reauthorized credential belongs to another user: "
                f"expected={account.chatgpt_user_id} "
                f"actual={credential.chatgpt_user_id}"
            )
        confirmed_members = self._wait_for_member(
            space=space,
            admin=snapshot.admin,
            user_id=credential.chatgpt_user_id,
        )
        if not _member_present(confirmed_members, credential.chatgpt_user_id):
            raise RuntimeError(
                "reauthorized account is no longer present in the target space: "
                f"user_id={credential.chatgpt_user_id}"
            )
        payload = build_sub2api_codex_payload(
            space=space,
            credential=credential,
        )
        updated = self._downstream.apply_codex_credential(
            account_id=account.id,
            payload=payload,
            idempotency_key=sub2api_idempotency_key(
                space_id=space.external_space_id,
                chatgpt_user_id=credential.chatgpt_user_id,
                access_token=credential.access_token,
            ),
        )
        if updated.id != account.id:
            raise RuntimeError(
                "Sub2API reauthorization updated an unexpected account: "
                f"expected={account.id} actual={updated.id}"
            )
        context["new_chatgpt_user_id"] = credential.chatgpt_user_id
        context["downstream_account_id"] = updated.id
        return "succeeded", "reauthorize", "downstream_401_reauthorized_and_pushed"

    def _recover_pushed_replacement(
        self,
        *,
        space: SpaceReplenishmentConfig,
        snapshot: SpaceRemoteSnapshot,
        downstream_accounts: list[Sub2APIAccount],
        admin_user_ids: set[str],
        context: dict[str, object],
    ) -> tuple[str, str, str] | None:
        by_user_id = {
            account.chatgpt_user_id: account
            for account in downstream_accounts
            if account.chatgpt_user_id
        }
        remote_user_ids = {member.user_id for member in snapshot.members}
        for new_account in sorted(downstream_accounts, key=lambda account: account.id):
            old_user_id = new_account.replacement_for_user_id
            if not old_user_id or new_account.replacement_space_id != space.external_space_id:
                continue
            if (
                old_user_id in admin_user_ids
                or new_account.chatgpt_user_id in admin_user_ids
            ):
                continue
            old_account = by_user_id.get(old_user_id)
            if old_account is None and old_user_id not in remote_user_ids:
                continue
            context["_action"] = "recover_replacement"
            context["new_email"] = new_account.email
            context["new_chatgpt_user_id"] = new_account.chatgpt_user_id
            context["replaced_chatgpt_user_id"] = old_user_id
            context["downstream_account_id"] = new_account.id
            if new_account.chatgpt_user_id not in remote_user_ids:
                self._downstream.delete_account(new_account.id)
                return (
                    "waiting",
                    "recover_replacement",
                    "replacement_new_remote_member_missing",
                )
            if old_user_id in remote_user_ids:
                try:
                    self._gateway.remove_member(space, snapshot.admin, user_id=old_user_id)
                except Exception:
                    pass
                members = self._wait_for_member_absent(
                    space=space,
                    admin=snapshot.admin,
                    user_id=old_user_id,
                )
                if _member_present(members, old_user_id):
                    return "waiting", "recover_replacement", "old_remote_member_still_present"
            if old_account is not None:
                self._downstream.delete_account(old_account.id)
                context["removed_downstream_account_id"] = old_account.id
            return "succeeded", "recover_replacement", "replacement_recovered"
        return None

    def _replacement_target(
        self,
        *,
        space: SpaceReplenishmentConfig,
        member_accounts: list[Sub2APIAccount],
    ) -> Sub2APIAccount | None:
        exhausted: list[tuple[float, Sub2APIAccount]] = []
        now = self._now()
        for account in member_accounts:
            signal = resolve_usage_signal(
                account,
                credential_type=space.credential_type,
                now=now,
                stale_after_s=self._usage_stale_after_s,
            )
            if signal.usable and signal.used_percent >= self._usage_threshold_percent:
                exhausted.append((signal.used_percent, account))
        if exhausted:
            exhausted.sort(key=lambda item: (-item[0], item[1].id))
            return exhausted[0][1]

        error_accounts = [
            account
            for account in member_accounts
            if account.status.strip().casefold() == "error"
        ]
        if error_accounts:
            return min(error_accounts, key=lambda account: account.id)
        return None

    def _select_invite_email(
        self,
        *,
        space: SpaceReplenishmentConfig,
        snapshot: SpaceRemoteSnapshot,
        excluded_emails: set[str] | None = None,
    ) -> str:
        excluded = excluded_emails or set()
        for invite in snapshot.invites:
            email = invite.email.strip()
            if not email or "@" not in email:
                continue
            if email.casefold() in excluded:
                continue
            if self._candidate_in_cooldown(space.external_space_id, email):
                continue
            return email
        return ""

    def _remove_remote_member_and_confirm(
        self,
        *,
        space: SpaceReplenishmentConfig,
        snapshot: SpaceRemoteSnapshot,
        user_id: str,
    ) -> bool:
        if not _member_present(snapshot.members, user_id):
            return True
        try:
            self._gateway.remove_member(
                space,
                snapshot.admin,
                user_id=user_id,
            )
        except Exception:
            # The remote mutation may have committed even when its response was lost.
            pass
        members = self._wait_for_member_absent(
            space=space,
            admin=snapshot.admin,
            user_id=user_id,
        )
        return not _member_present(members, user_id)

    def _wait_for_member(
        self,
        *,
        space: SpaceReplenishmentConfig,
        admin: SpaceAdminContext,
        user_id: str,
    ) -> tuple[RemoteMember, ...]:
        members: tuple[RemoteMember, ...] = ()
        for attempt in range(self._member_confirm_attempts):
            members = self._gateway.list_members(space, admin)
            if _member_present(members, user_id):
                return members
            if attempt + 1 < self._member_confirm_attempts:
                self._sleep(self._member_confirm_interval_s)
        return members

    def _wait_for_member_absent(
        self,
        *,
        space: SpaceReplenishmentConfig,
        admin: SpaceAdminContext,
        user_id: str,
    ) -> tuple[RemoteMember, ...]:
        members: tuple[RemoteMember, ...] = ()
        for attempt in range(self._member_confirm_attempts):
            members = self._gateway.list_members(space, admin)
            if not _member_present(members, user_id):
                return members
            if attempt + 1 < self._member_confirm_attempts:
                self._sleep(self._member_confirm_interval_s)
        return members

    def _remove_remote_invite_and_confirm(
        self,
        *,
        space: SpaceReplenishmentConfig,
        snapshot: SpaceRemoteSnapshot,
        email: str,
    ) -> bool:
        try:
            self._gateway.revoke_invite(
                space,
                snapshot.admin,
                email=email,
            )
        except Exception:
            # The remote mutation may have committed even when its response was lost.
            pass
        refreshed = self._gateway.snapshot(space)
        target = email.strip().casefold()
        return not any(invite.email.strip().casefold() == target for invite in refreshed.invites)

    def _candidate_in_cooldown(self, space_id: str, email: str) -> bool:
        key = (space_id, email.casefold())
        now = self._now()
        with self._cooldown_lock:
            expires_at = self._candidate_cooldowns.get(key)
            if expires_at is None:
                return False
            if now >= expires_at:
                self._candidate_cooldowns.pop(key, None)
                return False
            return True

    def _mark_candidate_cooldown(self, space_id: str, email: str) -> None:
        if self._candidate_failure_cooldown_s <= 0:
            return
        key = (space_id, email.casefold())
        with self._cooldown_lock:
            self._candidate_cooldowns[key] = self._now() + timedelta(
                seconds=self._candidate_failure_cooldown_s
            )

    def _now(self) -> datetime:
        value = self._now_fn()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _admin_user_ids(snapshot: SpaceRemoteSnapshot) -> set[str]:
    admin_user_ids = {
        member.user_id
        for member in snapshot.members
        if member.role.strip().lower() in {"owner", "admin", "account-owner"}
    }
    configured_admin_user_id = snapshot.admin.admin_user_id
    if configured_admin_user_id and any(
        member.user_id == configured_admin_user_id for member in snapshot.members
    ):
        admin_user_ids.add(configured_admin_user_id)
    return admin_user_ids


def _non_admin_members(
    snapshot: SpaceRemoteSnapshot,
    admin_user_ids: set[str],
) -> tuple[RemoteMember, ...]:
    return tuple(
        member for member in snapshot.members if member.user_id not in admin_user_ids
    )


def _member_present(members: tuple[RemoteMember, ...], user_id: str) -> bool:
    return any(member.user_id == user_id for member in members)


def _member_by_email(
    members: tuple[RemoteMember, ...],
    email: str,
) -> RemoteMember | None:
    target = str(email or "").strip().casefold()
    if not target:
        return None
    return next(
        (member for member in members if member.email.strip().casefold() == target),
        None,
    )


def _account_by_user_id(
    accounts: list[Sub2APIAccount],
    user_id: str,
) -> Sub2APIAccount | None:
    return next((account for account in accounts if account.chatgpt_user_id == user_id), None)
