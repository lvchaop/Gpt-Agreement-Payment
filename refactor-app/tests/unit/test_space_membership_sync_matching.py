from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from refactor_app.application.workflows import space_membership_invite_sync as invite_sync
from refactor_app.application.workflows.space_membership_invite_sync import (
    SpaceMembershipInviteSyncInput,
    _account_by_openai_user_id,
    _match_member_account,
    _select_invite_candidates,
    _select_invite_spaces,
)
from refactor_app.infrastructure.db.models import SpaceReplenishEmailModel


class _ScalarRows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def scalars(self, _statement: object) -> _ScalarRows:
        return _ScalarRows(self._rows)


def test_account_by_openai_user_id_indexes_bare_and_workspace_suffixed_ids() -> None:
    account = SimpleNamespace(
        id="account-1",
        openai_user_id="user-ON0K8PUL5vaYOUqqf1ejeZkX__4fa7a76b-fe3b-46a6-ae44-5c581077c899",
    )

    result = _account_by_openai_user_id(session=_Session([account]))  # type: ignore[arg-type]

    assert result["user-ON0K8PUL5vaYOUqqf1ejeZkX"] is account
    assert (
        result["user-ON0K8PUL5vaYOUqqf1ejeZkX__4fa7a76b-fe3b-46a6-ae44-5c581077c899"]
        is account
    )


def test_match_member_account_uses_remote_user_id_against_normalized_local_openai_user_id() -> None:
    account = SimpleNamespace(id="account-1")
    member = {
        "id": "user-ON0K8PUL5vaYOUqqf1ejeZkX",
        "account_user_id": "user-ON0K8PUL5vaYOUqqf1ejeZkX__4fa7a76b-fe3b-46a6-ae44-5c581077c899",
        "email": None,
        "verified_email": None,
    }

    matched = _match_member_account(
        member=member,
        account_by_email={},
        account_by_openai_user_id={
            "user-ON0K8PUL5vaYOUqqf1ejeZkX": account,
            "user-ON0K8PUL5vaYOUqqf1ejeZkX__4fa7a76b-fe3b-46a6-ae44-5c581077c899": account,
        },
    )

    assert matched is account


def test_remote_invite_only_inserts_missing_active_account_as_active(
    monkeypatch,
) -> None:
    active_account = SimpleNamespace(
        id="active-account",
        email="active@example.test",
        account_status="active",
    )
    inactive_account = SimpleNamespace(
        id="inactive-account",
        email="inactive@example.test",
        account_status="invalid",
    )
    existing_account = SimpleNamespace(
        id="existing-account",
        email="existing@example.test",
        account_status="active",
    )
    existing_membership = SimpleNamespace(
        space_id="space-1",
        user_account_id=existing_account.id,
        membership_status="failed",
    )

    class MembershipSession:
        def __init__(self) -> None:
            self.memberships = {existing_account.id: existing_membership}

        def scalars(self, statement: object) -> _ScalarRows:
            entity = statement.column_descriptions[0].get("entity")
            if entity is SpaceReplenishEmailModel:
                return _ScalarRows([])
            account_id = next(
                value
                for key, value in statement.compile().params.items()
                if "user_account_id" in key
            )
            membership = self.memberships.get(str(account_id))
            return _ScalarRows([membership] if membership is not None else [])

        def add(self, membership: Any) -> None:
            self.memberships[membership.user_account_id] = membership

    class Provider:
        def fetch_subscription(self, **_kwargs: Any) -> dict:
            return {}

        def list_account_users(self, **_kwargs: Any) -> list[dict]:
            return []

        def list_account_invites(self, **_kwargs: Any) -> list[dict]:
            return [
                {"email_address": active_account.email},
                {"email_address": inactive_account.email},
                {"email_address": existing_account.email},
            ]

    session = MembershipSession()
    seen_account_ids: set[str] = set()
    monkeypatch.setattr(
        invite_sync,
        "_admin_session",
        lambda **_kwargs: SimpleNamespace(
            id="admin-1",
            access_token="admin-token",
            cookie_header="session=cookie",
        ),
    )
    monkeypatch.setattr(
        invite_sync,
        "ensure_team_admin_static_proxy_url_in_session",
        lambda **_kwargs: "http://proxy.example.test:8080",
    )
    monkeypatch.setattr(
        invite_sync,
        "_account_by_email",
        lambda **_kwargs: {
            active_account.email: active_account,
            inactive_account.email: inactive_account,
            existing_account.email: existing_account,
        },
    )
    monkeypatch.setattr(invite_sync, "_account_by_openai_user_id", lambda **_kwargs: {})

    def capture_stale_memberships(**kwargs: Any) -> int:
        seen_account_ids.update(kwargs["seen_user_account_ids"])
        return 0

    monkeypatch.setattr(invite_sync, "_delete_stale_memberships", capture_stale_memberships)

    stats = invite_sync._sync_remote_memberships(
        session=session,  # type: ignore[arg-type]
        space=SimpleNamespace(id="space-1", external_space_id="workspace-1"),
        page_size=100,
        bind_reason="test",
        openai_provider=Provider(),  # type: ignore[arg-type]
    )

    assert stats["synced_invited_count"] == 1
    assert session.memberships[active_account.id].membership_status == "active"
    assert inactive_account.id not in session.memberships
    assert session.memberships[existing_account.id] is existing_membership
    assert existing_membership.membership_status == "failed"
    assert seen_account_ids == {
        active_account.id,
        inactive_account.id,
        existing_account.id,
    }


def test_select_invite_candidates_uses_random_order() -> None:
    statements: list[object] = []

    class CaptureSession:
        def scalars(self, statement: object) -> _ScalarRows:
            statements.append(statement)
            return _ScalarRows([])

    assert _select_invite_candidates(
        session=CaptureSession(),  # type: ignore[arg-type]
        space_id="space-1",
        limit=350,
    ) == []

    assert "ORDER BY random()" in str(statements[0])


def test_select_invite_spaces_filters_requested_active_business_space() -> None:
    selected = SimpleNamespace(id="space-target")
    statements: list[object] = []

    class CaptureSession:
        def scalars(self, statement: object) -> _ScalarRows:
            statements.append(statement)
            return _ScalarRows([selected])

    result = _select_invite_spaces(
        session=CaptureSession(),  # type: ignore[arg-type]
        input_=SpaceMembershipInviteSyncInput(space_id="space-target"),
    )

    compiled = statements[0].compile()
    assert result == [selected]
    assert "space-target" in compiled.params.values()
    assert "spaces.space_type" in str(statements[0])
    assert "spaces.space_status" in str(statements[0])


def test_sync_remote_replenish_email_statuses_confirms_remote_and_releases_missing() -> None:
    now = datetime.now(UTC)
    confirmed_row = SpaceReplenishEmailModel(
        id="replenish-confirmed",
        email="confirmed@example.test",
        email_key="confirmed@example.test",
        source_type="local_inventory",
        space_id="space-1",
        space_credential_id="",
        replaces_space_credential_id="",
        invite_batch_id="batch-1",
        invite_status="confirm_pending",
        process_status="idle",
        created_at=now,
        updated_at=now,
    )
    released_row = SpaceReplenishEmailModel(
        id="replenish-release",
        email="released@example.test",
        email_key="released@example.test",
        source_type="local_inventory",
        space_id="space-1",
        space_credential_id="",
        replaces_space_credential_id="",
        invite_batch_id="batch-1",
        invite_status="confirm_pending",
        process_status="idle",
        invite_confirm_after=now,
        created_at=now,
        updated_at=now,
    )
    completed_row = SpaceReplenishEmailModel(
        id="replenish-completed",
        email="completed@example.test",
        email_key="completed@example.test",
        source_type="local_inventory",
        space_id="space-1",
        invite_status="confirmed",
        process_status="completed",
        space_credential_id="credential-1",
        invite_confirmed_at=now,
        created_at=now,
        updated_at=now,
    )

    class ReplenishSession:
        def __init__(self, rows: list[SpaceReplenishEmailModel]) -> None:
            self.rows = rows

        def scalars(self, statement: object) -> _ScalarRows:
            entity = statement.column_descriptions[0].get("entity")
            if entity is not SpaceReplenishEmailModel:
                return _ScalarRows([])
            return _ScalarRows(
                [
                    row
                    for row in self.rows
                    if row.space_id == "space-1"
                    and row.source_type == "local_inventory"
                    and row.space_credential_id == ""
                    and row.replaces_space_credential_id == ""
                    and row.process_status in ("idle", "failed")
                    and row.invite_status in ("confirm_pending", "confirmed", "failed")
                ]
            )

    stats = invite_sync._sync_remote_replenish_email_statuses(
        session=ReplenishSession([confirmed_row, released_row, completed_row]),  # type: ignore[arg-type]
        space=SimpleNamespace(id="space-1"),
        remote_invites=[{"email_address": "confirmed@example.test"}],
        now=now,
    )

    assert stats == {
        "synced_replenish_confirmed_count": 1,
        "released_replenish_count": 1,
    }
    assert confirmed_row.invite_status == "confirmed"
    assert confirmed_row.invite_confirm_after is None
    assert confirmed_row.invite_confirmed_at == now
    assert confirmed_row.failure_code == ""
    assert confirmed_row.failure_message == ""

    assert released_row.space_id is None
    assert released_row.user_account_id is None
    assert released_row.invite_batch_id == ""
    assert released_row.invite_status == "available"
    assert released_row.process_status == "idle"
    assert released_row.invite_confirm_after is None
    assert released_row.invite_confirmed_at is None
    assert released_row.retry_count == 0

    assert completed_row.space_id == "space-1"
    assert completed_row.invite_status == "confirmed"
    assert completed_row.process_status == "completed"
    assert completed_row.space_credential_id == "credential-1"
