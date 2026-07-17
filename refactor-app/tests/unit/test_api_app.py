from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import delete

from refactor_app.api.app import create_app
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    JobModel,
    SpaceMembershipModel,
    SpaceModel,
    TeamAdminSessionModel,
    UserAccountModel,
)


def _disable_web_login(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("REFACTOR_APP_WEB_LOGIN_PASSWORD", "")


def test_create_app_registers_p8_routes(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    app = create_app()

    paths = set(app.openapi()["paths"])

    assert app.title == "refactor-app"
    assert "/health" in paths
    assert "/jobs" in paths
    assert "/user-accounts" in paths
    assert "/user-accounts/{user_account_id}/access-token" in paths
    assert "/user-accounts/delete-selected" in paths
    assert "/account-email-change/jobs" in paths
    assert "/spaces" in paths
    assert "/memberships/personal-codex-authorize-job" in paths
    assert "/space-credentials" in paths
    assert "/space-credentials/business-access-token-job" in paths
    assert "/space-credentials/push-job" in paths
    assert "/spaces/recycle-sweep-job" in paths
    assert "/team-workspaces" not in paths
    assert "/codex-credentials" not in paths
    assert "/workspace-join-batches" not in paths
    assert "/downstream-push-records" not in paths
    assert "/proxies" in paths
    assert "/mail/allocate-job" in paths
    assert "/mail/poll-otp-job" in paths
    assert "/mail/mark-used-job" in paths
    assert "/mail/mark-failed-job" in paths
    assert "/mail/release-job" in paths
    assert "/ops" in paths


def test_ops_ui_serves_minimal_operations_page(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())

    response = client.get("/ops")

    assert response.status_code == 200
    assert '<div id="app"></div>' in response.text
    assert "/ops/assets/" in response.text


def test_create_job_api_enqueues_job(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    response = client.post(
        "/jobs",
        json={"type": "test.api.enqueue", "input_json": {"value": "ok"}, "created_by": "test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_status"] == "queued"

    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    with session_factory() as session:
        job = session.get(JobModel, body["job_id"])
        assert job is not None
        assert job.type == "test.api.enqueue"
        session.execute(delete(JobModel).where(JobModel.id == body["job_id"]))
        session.commit()


def test_delete_selected_user_accounts(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    account_ids = [f"test-bulk-delete-{uuid4()}" for _ in range(2)]
    missing_id = f"test-bulk-delete-missing-{uuid4()}"
    now = datetime.now(UTC)

    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    with session_factory() as session:
        session.add_all(
            UserAccountModel(
                id=account_id,
                email=f"{account_id}@example.com",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
            for account_id in account_ids
        )
        session.commit()

    try:
        response = client.post(
            "/user-accounts/delete-selected",
            json={"user_account_ids": [account_ids[0], account_ids[0], account_ids[1], missing_id]},
        )

        assert response.status_code == 200
        assert response.json() == {
            "requested_count": 3,
            "deleted_count": 2,
            "missing_count": 1,
            "deleted_proxy_bindings": 0,
        }
        with session_factory() as session:
            assert session.get(UserAccountModel, account_ids[0]) is None
            assert session.get(UserAccountModel, account_ids[1]) is None
    finally:
        with session_factory() as session:
            session.execute(delete(UserAccountModel).where(UserAccountModel.id.in_(account_ids)))
            session.commit()


def test_get_user_account_access_token_reads_single_account(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    account_id = f"test-access-token-{uuid4()}"
    empty_account_id = f"test-access-token-empty-{uuid4()}"
    now = datetime.now(UTC)
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    with session_factory() as session:
        session.add_all(
            [
                UserAccountModel(
                    id=account_id,
                    email=f"{account_id}@example.com",
                    access_token="personal-session-access-token",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                ),
                UserAccountModel(
                    id=empty_account_id,
                    email=f"{empty_account_id}@example.com",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()

    try:
        response = client.get(f"/user-accounts/{account_id}/access-token")
        assert response.status_code == 200
        assert response.json() == {
            "user_account_id": account_id,
            "access_token": "personal-session-access-token",
        }

        list_response = client.get("/user-accounts", params={"q": account_id})
        item = list_response.json()["items"][0]
        assert item["has_access_token"] is True
        assert "access_token" not in item

        empty_response = client.get(f"/user-accounts/{empty_account_id}/access-token")
        assert empty_response.status_code == 409
        assert empty_response.json()["detail"] == "account access_token is empty"
    finally:
        with session_factory() as session:
            session.execute(
                delete(UserAccountModel).where(
                    UserAccountModel.id.in_([account_id, empty_account_id])
                )
            )
            session.commit()


def test_account_and_space_session_recency_filters(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    prefix = f"test-session-recency-{uuid4()}"
    account_ids = {
        "recent": f"{prefix}-account-recent",
        "stale": f"{prefix}-account-stale",
        "never": f"{prefix}-account-never",
    }
    space_ids = {
        "recent": f"{prefix}-space-recent",
        "stale": f"{prefix}-space-stale",
        "never": f"{prefix}-space-never",
        "business": f"{prefix}-space-business",
    }
    membership_ids = {
        "recent": f"{prefix}-membership-recent",
        "stale": f"{prefix}-membership-stale",
        "never": f"{prefix}-membership-never",
        "business": f"{prefix}-membership-business",
    }
    admin_session_id = f"{prefix}-admin-session"
    now = datetime.now(UTC)
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))

    with session_factory() as session:
        session.add_all(
            [
                UserAccountModel(
                    id=account_ids["recent"],
                    email=f"{prefix}-recent@example.com",
                    account_status="active",
                    codex_select_channel_required=True,
                    codex_select_channel_detected_at=now - timedelta(hours=1),
                    last_session_refresh_at=now - timedelta(hours=4),
                    created_at=now,
                    updated_at=now,
                ),
                UserAccountModel(
                    id=account_ids["stale"],
                    email=f"{prefix}-stale@example.com",
                    account_status="active",
                    last_session_refresh_at=now - timedelta(hours=10),
                    created_at=now,
                    updated_at=now,
                ),
                UserAccountModel(
                    id=account_ids["never"],
                    email=f"{prefix}-never@example.com",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                ),
                TeamAdminSessionModel(
                    id=admin_session_id,
                    admin_email=f"{prefix}-admin@example.com",
                    raw_session_json={},
                    imported_at=now - timedelta(hours=5),
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        for key in ("recent", "stale", "never"):
            session.add(
                SpaceModel(
                    id=space_ids[key],
                    external_space_id=f"{prefix}-external-{key}",
                    owner_user_account_id=account_ids[key],
                    name=f"{prefix}-{key}",
                    space_type="personal",
                    auth_mode="codex_oauth",
                    credential_type="personal_account",
                    plan_type="plus" if key == "recent" else "free",
                    space_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add(
            SpaceModel(
                id=space_ids["business"],
                external_space_id=f"{prefix}-external-business",
                name=f"{prefix}-business",
                space_type="business",
                auth_mode="backend_access_token",
                credential_type="team_monthly",
                plan_type="team",
                space_status="active",
                source_admin_session_id=admin_session_id,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        for key in ("recent", "stale", "never"):
            session.add(
                SpaceMembershipModel(
                    id=membership_ids[key],
                    space_id=space_ids[key],
                    user_account_id=account_ids[key],
                    membership_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add(
            SpaceMembershipModel(
                id=membership_ids["business"],
                space_id=space_ids["business"],
                user_account_id=account_ids["recent"],
                membership_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    try:
        account_response = client.get(
            "/user-accounts",
            params={"q": prefix, "session_recency": "within_6h", "page_size": 20},
        )
        assert account_response.status_code == 200
        account_items = {item["id"]: item for item in account_response.json()["items"]}
        assert set(account_items) == {
            account_ids["recent"]
        }
        assert account_items[account_ids["recent"]]["personal_plan_type"] == "plus"
        assert account_items[account_ids["recent"]]["codex_select_channel_required"] is True
        assert account_items[account_ids["recent"]]["codex_select_channel_detected_at"]

        account_select_channel_response = client.get(
            "/user-accounts",
            params={
                "q": prefix,
                "codex_select_channel_required": "true",
                "page_size": 20,
            },
        )
        assert account_select_channel_response.status_code == 200
        assert {
            item["id"] for item in account_select_channel_response.json()["items"]
        } == {account_ids["recent"]}

        account_plan_response = client.get(
            "/user-accounts",
            params={"q": prefix, "personal_plan_type": "plus", "page_size": 20},
        )
        assert account_plan_response.status_code == 200
        assert {item["id"] for item in account_plan_response.json()["items"]} == {
            account_ids["recent"]
        }

        account_plan_sort_response = client.get(
            "/user-accounts",
            params={"q": prefix, "sort": "personal_plan_type", "page_size": 20},
        )
        assert account_plan_sort_response.status_code == 200
        account_plan_types = [
            item["personal_plan_type"]
            for item in account_plan_sort_response.json()["items"]
        ]
        assert account_plan_types == sorted(account_plan_types)

        account_never_response = client.get(
            "/user-accounts",
            params={"q": prefix, "session_recency": "never", "page_size": 20},
        )
        assert {item["id"] for item in account_never_response.json()["items"]} == {
            account_ids["never"]
        }

        space_response = client.get(
            "/spaces",
            params={"q": prefix, "session_recency": "within_6h", "page_size": 20},
        )
        assert space_response.status_code == 200
        space_items = {item["id"]: item for item in space_response.json()["items"]}
        assert set(space_items) == {space_ids["recent"], space_ids["business"]}
        assert space_items[space_ids["recent"]]["plan_type"] == "plus"
        assert space_items[space_ids["recent"]]["last_session_refresh_at"]
        assert space_items[space_ids["business"]]["last_session_refresh_at"]

        space_never_response = client.get(
            "/spaces",
            params={"q": prefix, "session_recency": "never", "page_size": 20},
        )
        assert {item["id"] for item in space_never_response.json()["items"]} == {
            space_ids["never"]
        }

        membership_response = client.get(
            "/memberships",
            params={"q": prefix, "session_recency": "within_6h", "page_size": 20},
        )
        assert membership_response.status_code == 200
        membership_items = {
            item["id"]: item for item in membership_response.json()["items"]
        }
        assert set(membership_items) == {
            membership_ids["recent"],
            membership_ids["business"],
        }
        assert membership_items[membership_ids["recent"]]["space_plan_type"] == "plus"
        assert membership_items[membership_ids["recent"]]["last_session_refresh_at"]
        assert (
            membership_items[membership_ids["recent"]]["codex_select_channel_required"]
            is True
        )

        membership_select_channel_response = client.get(
            "/memberships",
            params={
                "q": prefix,
                "codex_select_channel_required": "true",
                "page_size": 20,
            },
        )
        assert membership_select_channel_response.status_code == 200
        assert {
            item["id"] for item in membership_select_channel_response.json()["items"]
        } == {
            membership_ids["recent"],
            membership_ids["business"],
        }

        membership_plan_response = client.get(
            "/memberships",
            params={"q": prefix, "plan_type": "plus", "page_size": 20},
        )
        assert {item["id"] for item in membership_plan_response.json()["items"]} == {
            membership_ids["recent"]
        }

        membership_never_response = client.get(
            "/memberships",
            params={"q": prefix, "session_recency": "never", "page_size": 20},
        )
        assert {item["id"] for item in membership_never_response.json()["items"]} == {
            membership_ids["never"]
        }
    finally:
        with session_factory() as session:
            session.execute(delete(SpaceModel).where(SpaceModel.id.in_(space_ids.values())))
            session.execute(
                delete(TeamAdminSessionModel).where(TeamAdminSessionModel.id == admin_session_id)
            )
            session.execute(
                delete(UserAccountModel).where(UserAccountModel.id.in_(account_ids.values()))
            )
            session.commit()


def test_legacy_team_workspace_import_route_is_not_exposed(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())

    response = client.post("/team-workspaces/import", json={})

    assert response.status_code == 404
