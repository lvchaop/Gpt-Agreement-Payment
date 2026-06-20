from __future__ import annotations

from sqlalchemy import delete, select

from refactor_app.application.jobs.handlers import register_core_handlers
from refactor_app.application.jobs.queue import JobQueue
from refactor_app.application.jobs.runner import JobRunner
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    JobEventModel,
    JobModel,
    JobRunModel,
    TeamWorkspaceModel,
)


def test_worker_executes_team_workspace_import_job() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    external_workspace_id = "handler-import-workspace"

    with session_factory() as session:
        session.execute(
            delete(TeamWorkspaceModel).where(
                TeamWorkspaceModel.external_workspace_id == external_workspace_id
            )
        )
        job = JobQueue(session).enqueue(
            job_type="team_workspace.import",
            input_json={
                "external_workspace_id": external_workspace_id,
                "name": "Handler Workspace",
                "plan_type": "team",
                "seat_limit": 30,
                "workspace_status": "active",
            },
            created_by="test",
        )
        job_id = job.id
        session.commit()

    runner = JobRunner(session_factory)
    register_core_handlers(runner, session_factory=session_factory, settings=settings)

    assert runner.run_one() == job_id

    with session_factory() as session:
        saved_job = session.get(JobModel, job_id)
        workspace = session.scalars(
            select(TeamWorkspaceModel).where(
                TeamWorkspaceModel.external_workspace_id == external_workspace_id
            )
        ).one()
        assert saved_job is not None
        assert saved_job.job_status == "succeeded"
        assert workspace.name == "Handler Workspace"
        assert workspace.seat_limit == 30

        run_ids = select(JobRunModel.id).where(JobRunModel.job_id == job_id)
        session.execute(delete(JobEventModel).where(JobEventModel.run_id.in_(run_ids)))
        session.execute(delete(JobRunModel).where(JobRunModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace.id))
        session.commit()
