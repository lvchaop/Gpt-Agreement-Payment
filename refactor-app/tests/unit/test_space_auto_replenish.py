from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx

from refactor_app.application.workflows import space_auto_replenish as auto
from refactor_app.application.workflows.space_auto_replenish import (
    InviteExecutorClient,
    SpaceAutoReplenishWorkflow,
)


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Session:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def scalars(self, _statement: Any) -> _Rows:
        return _Rows(self._rows)

    def commit(self) -> None:
        return None


def test_invite_executor_client_sends_one_batch_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"batch_id": "batch-1"})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = InviteExecutorClient(
        base_url="https://invite-executor.test",
        api_key="api-key",
        http_client=http_client,
    )

    result = client.create_batch(
        external_space_id="workspace-1",
        access_token="admin-token",
        cookie_header="session=cookie",
        emails=["first@example.test", "second@example.test"],
    )

    assert result == {"batch_id": "batch-1"}
    assert captured == {
        "authorization": "Bearer api-key",
        "body": {
            "external_space_id": "workspace-1",
            "access_token": "admin-token",
            "cookie_header": "session=cookie",
            "emails": ["first@example.test", "second@example.test"],
        },
    }


def test_invite_executor_client_sends_dynamic_replenishment_registration() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(202, json={"batch_id": "batch-dynamic"})

    client = InviteExecutorClient(
        base_url="https://invite-executor.test",
        api_key="api-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.create_batch(
        external_space_id="workspace-dynamic",
        access_token="workspace-token",
        cookie_header="session=admin-cookie",
        emails=["first@example.test"],
        replenishment={
            "admin_key": "admin@example.test",
            "admin_email": "Admin@example.test",
            "name": "Dynamic Space",
            "enabled": True,
            "credential_type": "team_monthly",
            "seat_limit": 999,
        },
    )

    assert result == {"batch_id": "batch-dynamic"}
    assert captured["replenishment"] == {
        "admin_key": "admin@example.test",
        "admin_email": "Admin@example.test",
        "name": "Dynamic Space",
        "enabled": True,
        "credential_type": "team_monthly",
        "seat_limit": 999,
    }


def test_invite_executor_client_upserts_replenishment_hosting() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"external_space_id": "workspace-1"})

    client = InviteExecutorClient(
        base_url="https://invite-executor.test",
        api_key="api-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    registration = {
        "admin_key": "admin@example.test",
        "admin_email": "Admin@example.test",
        "name": "Hosted Space",
        "enabled": True,
        "credential_type": "team_monthly",
        "seat_limit": 999,
        "admin_proxy_url": "http://static-proxy.test:8080",
        "admin_access_token": "admin-token",
        "admin_cookie_header": "session=admin-cookie",
    }

    result = client.upsert_replenishment_space(
        external_space_id="workspace-1",
        registration=registration,
    )

    assert result == {"external_space_id": "workspace-1"}
    assert captured == {
        "method": "PUT",
        "path": "/v1/replenishment/spaces/workspace-1",
        "authorization": "Bearer api-key",
        "body": registration,
    }


def test_invite_executor_client_unhosting_is_idempotent_for_missing_space() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/v1/replenishment/spaces/workspace-missing"
        assert request.headers.get("Authorization") == "Bearer api-key"
        return httpx.Response(404, json={"detail": "replenishment space not found"})

    client = InviteExecutorClient(
        base_url="https://invite-executor.test",
        api_key="api-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.delete_replenishment_space(
        external_space_id="workspace-missing"
    ) == {
        "removed": False,
        "external_space_id": "workspace-missing",
    }


def test_manual_hosting_registers_admin_context_then_enables_local_space(monkeypatch) -> None:
    space = SimpleNamespace(
        id="space-1",
        external_space_id="workspace-1",
        name="Hosted Space",
        credential_type="team_monthly",
        seat_limit=999,
        auto_replenish_enabled=False,
        updated_at=None,
    )
    admin = SimpleNamespace(
        id="admin-1",
        admin_email="Admin@example.test",
        access_token="admin-token",
        session_token="session-secret",
        cookie_header="oai-did=device-1",
    )
    sessions: list[Any] = []

    class Session:
        def __init__(self) -> None:
            self.commit_count = 0
            sessions.append(self)

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, model: Any, row_id: str, **_kwargs: Any) -> Any:
            if model is auto.SpaceModel and row_id == space.id:
                return space
            return None

        def commit(self) -> None:
            self.commit_count += 1

    captured: dict[str, Any] = {}
    monkeypatch.setattr(auto, "_active_business_space", lambda **_kwargs: space)
    monkeypatch.setattr(auto, "_admin_session", lambda **_kwargs: admin)
    monkeypatch.setattr(
        auto,
        "ensure_team_admin_static_proxy_url_in_session",
        lambda **_kwargs: "http://static-proxy.test:8080",
    )
    monkeypatch.setattr(
        auto.InviteExecutorClient,
        "upsert_replenishment_space",
        lambda _self, **kwargs: captured.update(kwargs) or {"state": "idle"},
    )

    result = auto.host_space_auto_replenishment(
        session_factory=Session,  # type: ignore[arg-type]
        invite_executor_base_url="https://invite-executor.test",
        invite_executor_api_key="api-key",
        space_id=space.id,
    )

    assert result["hosted"] is True
    assert space.auto_replenish_enabled is True
    assert [session.commit_count for session in sessions] == [1, 1]
    assert captured == {
        "external_space_id": "workspace-1",
        "registration": {
            "admin_key": "admin@example.test",
            "admin_email": "Admin@example.test",
            "name": "Hosted Space",
            "enabled": True,
            "credential_type": "team_monthly",
            "seat_limit": 999,
            "admin_proxy_url": "http://static-proxy.test:8080",
            "admin_access_token": "admin-token",
            "admin_cookie_header": (
                "__Secure-next-auth.session-token=session-secret; oai-did=device-1"
            ),
        },
    }


def test_manual_unhosting_removes_remote_then_disables_local_space(monkeypatch) -> None:
    space = SimpleNamespace(
        id="space-1",
        external_space_id="workspace-1",
        space_type="business",
        auto_replenish_enabled=True,
        updated_at=None,
    )
    sessions: list[Any] = []

    class Session:
        def __init__(self) -> None:
            self.commit_count = 0
            sessions.append(self)

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, model: Any, row_id: str, **_kwargs: Any) -> Any:
            if model is auto.SpaceModel and row_id == space.id:
                return space
            return None

        def commit(self) -> None:
            self.commit_count += 1

    removed: list[str] = []
    monkeypatch.setattr(
        auto.InviteExecutorClient,
        "delete_replenishment_space",
        lambda _self, *, external_space_id: (
            removed.append(external_space_id)
            or {"removed": True, "external_space_id": external_space_id}
        ),
    )

    result = auto.cancel_space_auto_replenishment_hosting(
        session_factory=Session,  # type: ignore[arg-type]
        invite_executor_base_url="https://invite-executor.test",
        invite_executor_api_key="api-key",
        space_id=space.id,
    )

    assert result == {
        "space_id": "space-1",
        "external_space_id": "workspace-1",
        "hosted": False,
        "remote_removed": True,
    }
    assert removed == ["workspace-1"]
    assert space.auto_replenish_enabled is False
    assert [session.commit_count for session in sessions] == [0, 1]


def test_team_admin_session_token_is_included_in_registered_cookie_header() -> None:
    admin = SimpleNamespace(
        cookie_header="oai-did=device-1",
        session_token="session-secret",
    )

    assert auto._team_admin_cookie_header(admin) == (
        "__Secure-next-auth.session-token=session-secret; oai-did=device-1"
    )


def test_invite_selection_uses_only_available_local_replenish_inventory() -> None:
    inventory_row = SimpleNamespace(id="inventory-1", email="local@example.test")

    class Session:
        def __init__(self) -> None:
            self.statements: list[Any] = []

        def scalars(self, statement: Any) -> _Rows:
            self.statements.append(statement)
            return _Rows([inventory_row])

    session = Session()
    workflow = SpaceAutoReplenishWorkflow(
        session_factory=lambda: None,  # type: ignore[arg-type]
        mail_provider=object(),  # type: ignore[arg-type]
        openai_provider=object(),  # type: ignore[arg-type]
        invite_executor_base_url="https://invite-executor.test",
        invite_executor_api_key="api-key",
    )

    selected = workflow._select_invite_candidates(  # noqa: SLF001
        session=session,  # type: ignore[arg-type]
        limit=1000,
    )

    assert selected == [inventory_row]
    assert len(session.statements) == 1
    statement = session.statements[0]
    sql = str(statement)
    params = set(statement.compile().params.values())
    assert "local_inventory" in params
    assert "available" in params
    assert "user_accounts.account_status" not in sql
    assert "user_accounts.session_status" not in sql
    assert "user_accounts.last_session_refresh_at" not in sql


def test_invite_confirmation_uses_only_remote_pending_invites(monkeypatch) -> None:
    rows = [
        SimpleNamespace(
            id="row-1",
            email="Confirmed@example.test",
            email_key="confirmed@example.test",
            invite_status="confirm_pending",
            process_status="idle",
            invite_confirmed_at=None,
            failure_code="",
            failure_message="",
            updated_at=None,
        ),
        SimpleNamespace(
            id="row-2",
            email="Missing@example.test",
            email_key="missing@example.test",
            invite_status="confirm_pending",
            process_status="idle",
            invite_confirmed_at=None,
            failure_code="",
            failure_message="",
            updated_at=None,
        ),
    ]
    sessions = iter([_Session(["row-1", "row-2"]), _Session(rows)])

    class Provider:
        def list_account_invites(self, **_kwargs: Any) -> list[dict]:
            return [{"email_address": "Confirmed@example.test"}]

    workflow = SpaceAutoReplenishWorkflow(
        session_factory=lambda: next(sessions),  # type: ignore[arg-type]
        mail_provider=object(),  # type: ignore[arg-type]
        openai_provider=Provider(),  # type: ignore[arg-type]
        invite_executor_base_url="https://invite-executor.test",
        invite_executor_api_key="api-key",
    )
    monkeypatch.setattr(
        workflow,
        "_admin_context",
        lambda **_kwargs: auto._AdminContext(
            space_id="space-1",
            external_space_id="workspace-1",
            access_token="admin-token",
            cookie_header="session=cookie",
            proxy_url="http://static-proxy.test:8080",
        ),
    )
    monkeypatch.setattr(workflow, "_event", lambda **_kwargs: None)

    result = workflow.reconcile_pending_invites(space_id="space-1")

    assert result == {"checked": 2, "confirmed": 1, "failed": 1}
    assert rows[0].invite_status == "confirmed"
    assert rows[0].process_status == "idle"
    assert rows[1].invite_status == "failed"
    assert rows[1].process_status == "failed"
    assert rows[1].failure_code == "remote_pending_invite_missing"


def test_admin_session_never_falls_back_to_another_space_admin() -> None:
    class Session:
        def get(self, _model: Any, row_id: str) -> object:
            return {"admin-1": "expected-admin"}.get(row_id)

        def scalars(self, _statement: Any) -> Any:
            raise AssertionError("automatic replenish must not query a fallback admin")

    session = Session()

    assert (
        auto._admin_session(
            session=session,  # type: ignore[arg-type]
            space=SimpleNamespace(source_admin_session_id=""),  # type: ignore[arg-type]
        )
        is None
    )
    assert (
        auto._admin_session(
            session=session,  # type: ignore[arg-type]
            space=SimpleNamespace(source_admin_session_id="admin-1"),  # type: ignore[arg-type]
        )
        == "expected-admin"
    )


def test_remote_seat_capacity_counts_the_admin_in_total_seats() -> None:
    assert not auto._has_remote_seat_capacity(
        remote_user_count=2,
        seat_limit=2,
        replacing=False,
    )
    assert auto._has_remote_seat_capacity(
        remote_user_count=2,
        seat_limit=2,
        replacing=True,
    )
    assert not auto._has_remote_seat_capacity(
        remote_user_count=3,
        seat_limit=2,
        replacing=True,
    )


def test_confirmed_member_removal_revokes_old_credential(monkeypatch) -> None:
    row = SimpleNamespace(
        id="replenish-1",
        space_id="space-1",
        replaces_space_credential_id="credential-old",
        process_status="remove_pending",
        completed_at=None,
        failure_code="old-error",
        failure_message="old-message",
        updated_at=None,
    )
    old_credential = SimpleNamespace(
        id="credential-old",
        user_account_id="account-old",
        credential_status="active",
        failure_code="old-error",
        failure_message="old-message",
        updated_at=None,
    )
    account = SimpleNamespace(id="account-old", email="old@example.test")
    membership = SimpleNamespace(
        space_id="space-1",
        user_account_id="account-old",
        remote_user_id="remote-user-old",
        remote_account_user_id="",
    )
    deleted: list[Any] = []

    class Session:
        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, model: Any, row_id: str) -> Any:
            if model is auto.SpaceReplenishEmailModel and row_id == row.id:
                return row
            if model is auto.SpaceCredentialModel and row_id == old_credential.id:
                return old_credential
            if model is auto.UserAccountModel and row_id == account.id:
                return account
            return None

        def scalar(self, _statement: Any) -> Any:
            return membership

        def delete(self, value: Any) -> None:
            deleted.append(value)

        def commit(self) -> None:
            return None

    class Provider:
        def remove_account_user(self, **_kwargs: Any) -> None:
            return None

        def list_account_users(self, **_kwargs: Any) -> list[dict]:
            return []

    workflow = SpaceAutoReplenishWorkflow(
        session_factory=Session,  # type: ignore[arg-type]
        mail_provider=object(),  # type: ignore[arg-type]
        openai_provider=Provider(),  # type: ignore[arg-type]
        invite_executor_base_url="https://invite-executor.test",
        invite_executor_api_key="api-key",
    )
    monkeypatch.setattr(
        workflow,
        "_admin_context",
        lambda **_kwargs: auto._AdminContext(
            space_id="space-1",
            external_space_id="workspace-1",
            access_token="admin-token",
            cookie_header="session=cookie",
            proxy_url="http://static-proxy.test:8080",
        ),
    )
    monkeypatch.setattr(workflow, "_event", lambda **_kwargs: None)

    result = workflow._remove_replaced_member(row_id=row.id, run_id="run-1")

    assert result == {"status": "completed", "removed_email": account.email}
    assert deleted == [membership]
    assert old_credential.credential_status == "revoked"
    assert old_credential.failure_code == ""
    assert old_credential.failure_message == ""
    assert old_credential.updated_at is not None
    assert row.process_status == "completed"
    assert row.completed_at is not None


def test_pushed_replacement_is_removed_in_the_same_space_cycle(monkeypatch) -> None:
    workflow = SpaceAutoReplenishWorkflow(
        session_factory=lambda: None,  # type: ignore[arg-type]
        mail_provider=object(),  # type: ignore[arg-type]
        openai_provider=object(),  # type: ignore[arg-type]
        invite_executor_base_url="https://invite-executor.test",
        invite_executor_api_key="api-key",
    )
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        workflow,
        "_complete_pushed_candidates",
        lambda *, space_id, run_id: calls.append(("complete", f"{space_id}:{run_id}")),
    )
    monkeypatch.setattr(
        workflow,
        "_pending_removal_row_id",
        lambda *, space_id: calls.append(("pending", space_id)) or "replenish-replacement",
    )
    monkeypatch.setattr(
        workflow,
        "_remove_replaced_member",
        lambda *, row_id, run_id: (
            calls.append(("remove", f"{row_id}:{run_id}"))
            or {"status": "completed", "removed_email": "old@example.test"}
        ),
    )

    result = workflow._complete_and_remove_replacement(
        space_id="space-1",
        run_id="run-1",
    )

    assert result == {"status": "completed", "removed_email": "old@example.test"}
    assert calls == [
        ("complete", "space-1:run-1"),
        ("pending", "space-1"),
        ("remove", "replenish-replacement:run-1"),
    ]
