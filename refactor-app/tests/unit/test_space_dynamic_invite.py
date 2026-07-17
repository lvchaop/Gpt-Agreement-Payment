from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from refactor_app.application.workflows import space_membership_invite_sync as invite_workflow
from refactor_app.application.workflows.space_membership_invite_sync import (
    SpaceDynamicMembershipInviteWorkflow,
    SpaceMembershipBatchInviteError,
    SpaceMembershipInviteSyncInput,
    SpaceMembershipInviteSyncWorkflow,
)
from refactor_app.infrastructure.db.models import (
    ProxyInventoryModel,
    SpaceMembershipModel,
    SpaceModel,
    TeamAdminSessionModel,
    UserAccountModel,
)
from refactor_app.plugins.openai_chatgpt.client import OpenAIChatGPTTimeoutError


class _ScalarRows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None


class _Store:
    def __init__(self) -> None:
        self.space = SimpleNamespace(
            id="space-1",
            external_space_id="workspace-1",
            seats_entitled=2,
            space_status="active",
        )
        self.admin = SimpleNamespace(
            id="admin-1",
            access_token="admin-access",
            cookie_header="session=cookie",
        )
        self.accounts = {
            "account-1": SimpleNamespace(id="account-1", email="ok@example.test"),
            "account-2": SimpleNamespace(id="account-2", email="bad@example.test"),
        }
        self.proxy = SimpleNamespace(
            id="proxy-1",
            provider="webshare",
            proxy_type="static_proxy",
            proxy_status="available",
            provider_valid=True,
            proxy_scheme="http",
            proxy_host="static-proxy.test",
            proxy_port=8080,
            proxy_username="",
            proxy_password="",
        )
        self.memberships: dict[str, SpaceMembershipModel] = {}


class _Session:
    def __init__(self, store: _Store) -> None:
        self.store = store

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, model: type[Any], key: str) -> Any | None:
        if model is SpaceModel and key == self.store.space.id:
            return self.store.space
        if model is TeamAdminSessionModel and key == self.store.admin.id:
            return self.store.admin
        if model is UserAccountModel:
            return self.store.accounts.get(key)
        if model is ProxyInventoryModel and key == self.store.proxy.id:
            return self.store.proxy
        return None

    def scalars(self, statement: Any) -> _ScalarRows:
        entity = statement.column_descriptions[0].get("entity")
        if entity is UserAccountModel:
            requested_ids = next(
                (
                    value
                    for value in statement.compile().params.values()
                    if isinstance(value, list)
                ),
                None,
            )
            if requested_ids is None:
                return _ScalarRows(list(self.store.accounts.values()))
            return _ScalarRows(
                [self.store.accounts[item] for item in requested_ids if item in self.store.accounts]
            )
        if entity is SpaceMembershipModel:
            account_id = next(
                (
                    value
                    for key, value in statement.compile().params.items()
                    if "user_account_id" in key
                ),
                "",
            )
            membership = self.store.memberships.get(str(account_id))
            return _ScalarRows([membership] if membership is not None else [])
        return _ScalarRows([])

    def add(self, row: Any) -> None:
        if isinstance(row, SpaceMembershipModel):
            self.store.memberships[row.user_account_id] = row

    def commit(self) -> None:
        return None


class _Provider:
    def __init__(self, *, timeout: bool = False) -> None:
        self.timeout = timeout
        self.proxy_url = ""
        self.proxy_resolve: tuple[str, ...] = ()
        self.email_batches: list[list[str]] = []
        self.single_emails: list[str] = []

    def invite_member(self, **kwargs: Any) -> dict:
        self.proxy_url = str(kwargs["proxy_url"])
        self.proxy_resolve = tuple(kwargs.get("proxy_resolve") or ())
        self.single_emails.append(str(kwargs["email"]))
        return {
            "account_invites": [{"email_address": str(kwargs["email"])}],
            "errored_emails": [],
        }

    def invite_members(self, **kwargs: Any) -> dict:
        self.proxy_url = str(kwargs["proxy_url"])
        emails = [str(item) for item in kwargs["emails"]]
        self.email_batches.append(emails)
        if self.timeout:
            raise OpenAIChatGPTTimeoutError("timed out")
        return {
            "account_invites": [
                {"email_address": email} for email in emails if email != "bad@example.test"
            ],
            "errored_emails": [
                {
                    "email_address": email,
                    "error": "Unable to invite user due to an error.",
                }
                for email in emails
                if email == "bad@example.test"
            ],
        }


def test_disabled_space_skips_queued_invite_work_without_upstream_call() -> None:
    store = _Store()
    store.space.space_status = "disabled"
    provider = _Provider()

    single_result = SpaceMembershipInviteSyncWorkflow(
        session_factory=lambda: _Session(store),
        openai_provider=provider,  # type: ignore[arg-type]
    ).run_invite_work(
        space_id="space-1",
        user_account_id="account-1",
        team_admin_session_id="admin-1",
    )
    batch_result = SpaceDynamicMembershipInviteWorkflow(
        session_factory=lambda: _Session(store),
        openai_provider=provider,  # type: ignore[arg-type]
        sleep_fn=lambda _seconds: None,
    ).run_batch_work(
        space_id="space-1",
        team_admin_session_id="admin-1",
        user_account_ids=["account-1", "account-2"],
    )

    assert single_result["skipped_reason"] == "space_not_active"
    assert batch_result["skipped_reason"] == "space_not_active"
    assert provider.email_batches == []


def test_single_invite_work_uses_direct_network() -> None:
    store = _Store()
    provider = _Provider()

    result = SpaceMembershipInviteSyncWorkflow(
        session_factory=lambda: _Session(store),
        openai_provider=provider,  # type: ignore[arg-type]
    ).run_invite_work(
        space_id="space-1",
        user_account_id="account-1",
        team_admin_session_id="admin-1",
    )

    assert "invite_proxy_id" not in result
    assert provider.proxy_url == ""
    assert provider.proxy_resolve == ()
    assert provider.single_emails == ["ok@example.test"]
    assert store.memberships["account-1"].membership_status == "invited"


def test_fixed_invite_workflow_enqueues_one_1000_party_barrier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = [SimpleNamespace(id=f"account-{index}") for index in range(1000)]
    queued: list[dict[str, Any]] = []
    admin = SimpleNamespace(id="admin-1", access_token="admin-access")
    space = SimpleNamespace(id="space-1")

    class FakeQueue:
        def __init__(self, _session: Any) -> None:
            pass

        def enqueue(self, **kwargs: Any) -> None:
            queued.append(kwargs)

    monkeypatch.setattr(invite_workflow, "_admin_session", lambda **_kwargs: admin)
    monkeypatch.setattr(
        invite_workflow,
        "_select_invite_candidates",
        lambda **_kwargs: accounts,
    )
    monkeypatch.setattr(invite_workflow, "WorkQueue", FakeQueue)

    workflow = SpaceMembershipInviteSyncWorkflow(
        session_factory=lambda: _Session(_Store()),
        openai_provider=_Provider(),  # type: ignore[arg-type]
    )
    stats = workflow._process_space(  # noqa: SLF001
        session=object(),  # type: ignore[arg-type]
        space=space,  # type: ignore[arg-type]
        input_=SpaceMembershipInviteSyncInput(),
        job_id="job-1",
        run_id="run-1",
    )

    inputs = [item["input_json"] for item in queued]
    assert stats["queued_invite_count"] == 1000
    assert len(inputs) == 1000
    assert {item["_barrier_key"] for item in inputs} == {"space-invite:job-1:space-1"}
    assert {item["_barrier_group"] for item in inputs} == {"all"}
    assert {item["_barrier_expected"] for item in inputs} == {1000}
    assert all("invite_proxy_id" not in item for item in inputs)
    assert all("invite_proxy_resolve" not in item for item in inputs)


def test_dynamic_batch_uses_static_proxy_and_only_writes_successes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    provider = _Provider()
    monkeypatch.setattr(
        invite_workflow,
        "ensure_team_admin_static_proxy_url_in_session",
        lambda **_kwargs: "http://static-proxy.test:8080",
    )
    workflow = SpaceDynamicMembershipInviteWorkflow(
        session_factory=lambda: _Session(store),
        openai_provider=provider,  # type: ignore[arg-type]
        sleep_fn=lambda _seconds: None,
    )

    with pytest.raises(SpaceMembershipBatchInviteError, match="partially failed"):
        workflow.run_batch_work(
            space_id="space-1",
            team_admin_session_id="admin-1",
            user_account_ids=["account-1", "account-2"],
        )

    assert provider.proxy_url == "http://static-proxy.test:8080"
    assert provider.email_batches == [["ok@example.test", "bad@example.test"]]
    assert store.memberships["account-1"].membership_status == "invited"
    assert "account-2" not in store.memberships


def test_dynamic_batch_timeout_marks_failed_then_waits_and_syncs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    provider = _Provider(timeout=True)
    events: list[str] = []
    monkeypatch.setattr(
        invite_workflow,
        "ensure_team_admin_static_proxy_url_in_session",
        lambda **_kwargs: "http://static-proxy.test:8080",
    )

    def fake_sync(**_kwargs: Any) -> dict[str, int]:
        assert {row.membership_status for row in store.memberships.values()} == {"failed"}
        assert set(store.memberships) == {"account-1", "account-2"}
        events.append("sync")
        store.memberships["account-1"].membership_status = "active"
        store.memberships.pop("account-2")
        return {
            "synced_active_count": 1,
            "synced_invited_count": 0,
            "deleted_stale_count": 1,
            "skipped_space_count": 0,
        }

    monkeypatch.setattr(invite_workflow, "_sync_remote_memberships", fake_sync)
    workflow = SpaceDynamicMembershipInviteWorkflow(
        session_factory=lambda: _Session(store),
        openai_provider=provider,  # type: ignore[arg-type]
        sleep_fn=lambda seconds: events.append(f"sleep:{seconds:g}"),
    )

    with pytest.raises(OpenAIChatGPTTimeoutError):
        workflow.run_batch_work(
            space_id="space-1",
            team_admin_session_id="admin-1",
            user_account_ids=["account-1", "account-2"],
        )

    assert events == ["sleep:30", "sync"]
    assert provider.email_batches == [["ok@example.test", "bad@example.test"]]
    assert store.memberships["account-1"].membership_status == "active"
    assert "account-2" not in store.memberships
