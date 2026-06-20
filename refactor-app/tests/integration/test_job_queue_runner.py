from __future__ import annotations

from sqlalchemy import delete, select

from refactor_app.application.jobs.queue import JobQueue
from refactor_app.application.jobs.runner import JobRunner
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import JobEventModel, JobModel, JobRunModel


def test_job_runner_executes_registered_handler_and_writes_events() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    job_type = "test.echo"

    with session_factory() as session:
        session.execute(delete(JobEventModel))
        session.execute(delete(JobRunModel))
        session.execute(delete(JobModel).where(JobModel.type == job_type))
        queue = JobQueue(session)
        job = queue.enqueue(job_type=job_type, input_json={"value": "ok"}, created_by="test")
        job_id = job.id
        session.commit()

    runner = JobRunner(session_factory)
    runner.register(job_type, lambda _session, input_json: {"echo": input_json["value"]})

    assert runner.run_one() == job_id

    with session_factory() as session:
        saved_job = session.get(JobModel, job_id)
        runs = session.scalars(select(JobRunModel).where(JobRunModel.job_id == job_id)).all()
        events = session.scalars(select(JobEventModel).where(JobEventModel.run_id == runs[0].id)).all()

        assert saved_job is not None
        assert saved_job.job_status == "succeeded"
        assert len(runs) == 1
        assert runs[0].run_status == "succeeded"
        assert runs[0].output_json == {"echo": "ok"}
        assert {event.event_type for event in events} == {"job.started", "job.succeeded"}

        session.execute(delete(JobEventModel).where(JobEventModel.run_id == runs[0].id))
        session.execute(delete(JobRunModel).where(JobRunModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()
