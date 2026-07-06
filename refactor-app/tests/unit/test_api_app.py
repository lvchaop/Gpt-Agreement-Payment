from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import delete

from refactor_app.api.app import create_app
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import JobModel


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
    assert "/spaces" in paths
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


def test_legacy_team_workspace_import_route_is_not_exposed(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())

    response = client.post("/team-workspaces/import", json={})

    assert response.status_code == 404
