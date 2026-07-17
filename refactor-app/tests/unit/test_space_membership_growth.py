from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from refactor_app.application.workflows import space_membership_growth as growth
from refactor_app.application.workflows.space_membership_growth import (
    SpaceMembershipGrowthWorkflow,
    growth_invite_count,
)
from refactor_app.infrastructure.db.models import SpaceModel, UserAccountModel


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Session:
    def __init__(self, *, space: Any, accounts: list[Any]) -> None:
        self.space = space
        self.accounts = accounts

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, model: type[Any], key: str) -> Any | None:
        if model is SpaceModel and key == self.space.id:
            return self.space
        return None

    def scalars(self, statement: Any) -> _Rows:
        entity = statement.column_descriptions[0].get("entity")
        if entity is UserAccountModel:
            return _Rows(self.accounts)
        return _Rows([])

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None


class _Provider:
    def __init__(self) -> None:
        self.email_batches: list[list[str]] = []
        self.user_batches: list[list[dict]] = []
        self.removals: list[dict[str, str]] = []

    def fetch_subscription(self, **_kwargs: Any) -> dict:
        return {"seats_entitled": 2, "seats_in_use": 1, "plan_type": "team"}

    def list_account_users(self, **_kwargs: Any) -> list[dict]:
        return self.user_batches.pop(0) if self.user_batches else []

    def list_account_invites(self, **_kwargs: Any) -> list[dict]:
        return []

    def invite_members(self, **kwargs: Any) -> dict:
        emails = [str(item) for item in kwargs["emails"]]
        self.email_batches.append(emails)
        return {
            "account_invites": [{"email_address": emails[0]}],
            "errored_emails": [{"email_address": emails[1], "error": "failed"}],
        }

    def remove_account_user(self, **kwargs: Any) -> dict:
        self.removals.append(
            {
                "account_id": str(kwargs["account_id"]),
                "user_id": str(kwargs["user_id"]),
                "proxy_url": str(kwargs["proxy_url"]),
            }
        )
        return {"ok": True}


def test_growth_invite_count_uses_remote_subscription_and_caps_at_sixteen() -> None:
    assert growth_invite_count(
        seats_entitled=2,
        seats_in_use=1,
        available_account_count=100,
    ) == 3
    assert growth_invite_count(
        seats_entitled=20,
        seats_in_use=20,
        available_account_count=100,
    ) == 16
    assert growth_invite_count(
        seats_entitled=999,
        seats_in_use=999,
        available_account_count=100,
    ) == 0


def test_growth_invite_work_sends_one_batch_and_enqueues_only_successful_accounts(
    monkeypatch,
) -> None:
    space = SimpleNamespace(
        id="space-1",
        external_space_id="workspace-1",
        space_type="business",
        space_status="active",
        seats_entitled=0,
        seat_limit=0,
        seats_in_use=0,
        plan_type="",
        raw_space_json={},
        last_subscription_sync_at=None,
        updated_at=None,
    )
    accounts = [
        SimpleNamespace(id="account-1", email="ok@example.test"),
        SimpleNamespace(id="account-2", email="bad@example.test"),
    ]
    queued: list[dict[str, Any]] = []

    class FakeQueue:
        def __init__(self, _session: Any) -> None:
            pass

        def enqueue(self, **kwargs: Any) -> Any:
            queued.append(kwargs)
            return SimpleNamespace(id=f"work-{len(queued)}")

    provider = _Provider()
    workflow = SpaceMembershipGrowthWorkflow(
        session_factory=lambda: _Session(space=space, accounts=accounts),
        openai_provider=provider,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        workflow,
        "_remote_context",
        lambda **_kwargs: growth._RemoteContext(
            space_id="space-1",
            external_space_id="workspace-1",
            admin_session_id="admin-1",
            access_token="admin-token",
            cookie_header="session=cookie",
            proxy_url="http://static-proxy.test:8080",
        ),
    )
    monkeypatch.setattr(growth, "_active_business_space", lambda **_kwargs: space)
    monkeypatch.setattr(growth, "_select_invite_candidates", lambda **_kwargs: accounts)
    monkeypatch.setattr(growth, "_upsert_invited_membership", lambda **_kwargs: None)
    monkeypatch.setattr(growth, "WorkQueue", FakeQueue)

    result = workflow.run_invite_batch_work(
        job_id="job-1",
        run_id="",
        space_id="space-1",
    )

    assert provider.email_batches == [["ok@example.test", "bad@example.test"]]
    assert result["invite_succeeded_count"] == 1
    assert result["invite_failed_count"] == 1
    assert [item["work_type"] for item in queued] == [
        "space.membership_growth.session",
        "space.membership_growth.finalize",
    ]
    assert queued[1]["input_json"]["user_account_ids"] == ["account-1"]
    assert queued[1]["input_json"]["session_work_ids"] == ["work-1"]


def test_growth_finalize_uses_remote_members_then_removes_one_confirmed_account(
    monkeypatch,
) -> None:
    provider = _Provider()
    joined_member = {"user_id": "user-joined", "email": "joined@example.test"}
    provider.user_batches = [[joined_member], []]
    account = SimpleNamespace(id="account-1", email="joined@example.test")
    workflow = SpaceMembershipGrowthWorkflow(
        session_factory=lambda: None,  # type: ignore[arg-type]
        openai_provider=provider,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        workflow,
        "_remote_context",
        lambda **_kwargs: growth._RemoteContext(
            space_id="space-1",
            external_space_id="workspace-1",
            admin_session_id="admin-1",
            access_token="admin-token",
            cookie_header="session=cookie",
            proxy_url="http://static-proxy.test:8080",
        ),
    )
    monkeypatch.setattr(
        workflow,
        "_wait_for_session_works",
        lambda **_kwargs: {"succeeded": 1, "skipped": 2, "failed": 0, "cancelled": 0},
    )
    monkeypatch.setattr(
        workflow,
        "_confirmed_members",
        lambda **_kwargs: [(account, joined_member)],
    )
    monkeypatch.setattr(workflow, "_sync_local", lambda **_kwargs: {"deleted_stale_count": 1})

    result = workflow.run_finalize_work(
        job_id="job-1",
        run_id="",
        space_id="space-1",
        user_account_ids=["account-1", "account-2", "account-3"],
        session_work_ids=["work-1", "work-2", "work-3"],
        session_wait_timeout_s=900,
    )

    assert result["confirmed_joined_count"] == 1
    assert result["removed_user_account_id"] == "account-1"
    assert provider.removals == [
        {
            "account_id": "workspace-1",
            "user_id": "user-joined",
            "proxy_url": "http://static-proxy.test:8080",
        }
    ]
