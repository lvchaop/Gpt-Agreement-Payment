from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from refactor_app.api.app import create_app
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import JobModel, TeamWorkspaceModel


def test_create_app_registers_p8_routes() -> None:
    app = create_app()

    paths = {route.path for route in app.routes}

    assert app.title == "refactor-app"
    assert "/health" in paths
    assert "/jobs" in paths
    assert "/user-accounts" in paths
    assert "/team-workspaces" in paths
    assert "/workspace-join-batches" in paths
    assert "/workspace-join-batches/{batch_id}/items" in paths
    assert "/memberships/invite-member-job" in paths
    assert "/proxies" in paths
    assert "/mail/allocate-job" in paths
    assert "/mail/poll-otp-job" in paths
    assert "/mail/mark-used-job" in paths
    assert "/mail/mark-failed-job" in paths
    assert "/mail/release-job" in paths
    assert "/ops" in paths


def test_ops_ui_serves_minimal_operations_page() -> None:
    client = TestClient(create_app())

    response = client.get("/ops")

    assert response.status_code == 200
    assert "Refactor Ops Console" in response.text
    assert "/ops/assets/" in response.text or "refactor-app 运维台" in response.text


def test_create_job_api_enqueues_job() -> None:
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


def test_import_team_workspace_api_upserts_by_provider_external_id() -> None:
    client = TestClient(create_app())
    payload = {
        "provider": "openai_chatgpt",
        "external_workspace_id": "api-upsert-workspace",
        "name": "Initial Workspace",
        "plan_type": "team",
        "seat_limit": 10,
        "workspace_status": "active",
    }

    first = client.post("/team-workspaces/import", json=payload)
    second = client.post(
        "/team-workspaces/import",
        json={**payload, "name": "Updated Workspace", "seat_limit": 20},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["team_workspace_id"] == second.json()["team_workspace_id"]

    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    with session_factory() as session:
        rows = session.scalars(
            select(TeamWorkspaceModel).where(
                TeamWorkspaceModel.provider == "openai_chatgpt",
                TeamWorkspaceModel.external_workspace_id == "api-upsert-workspace",
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].name == "Updated Workspace"
        assert rows[0].seat_limit == 20
        session.execute(
            delete(TeamWorkspaceModel).where(
                TeamWorkspaceModel.external_workspace_id == "api-upsert-workspace"
            )
        )
        session.commit()
