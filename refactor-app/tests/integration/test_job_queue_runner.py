from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete, select

from refactor_app.application.jobs.queue import JobQueue, WorkQueue
from refactor_app.application.jobs.runner import JobRunner
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import JobEventModel, JobModel, JobRunModel, WorkItemModel


def test_job_runner_executes_registered_handler_and_writes_events() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    job_type = "test.echo"

    with session_factory() as session:
        _skip_if_live_work_exists(session, job_type=job_type)
        test_job_ids = select(JobModel.id).where(JobModel.type == job_type)
        test_run_ids = select(JobRunModel.id).where(JobRunModel.job_id.in_(test_job_ids))
        session.execute(delete(JobEventModel).where(JobEventModel.run_id.in_(test_run_ids)))
        session.execute(delete(JobRunModel).where(JobRunModel.job_id.in_(test_job_ids)))
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id.in_(test_job_ids)))
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
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_limited_work_claims_up_to_job_concurrency() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    job_type = "test.concurrent-claim"

    with session_factory() as session:
        session.execute(
            delete(WorkItemModel).where(
                WorkItemModel.job_id.in_(select(JobModel.id).where(JobModel.type == job_type))
            )
        )
        session.execute(delete(JobModel).where(JobModel.type == job_type))
        queue = JobQueue(session)
        job = queue.enqueue(
            job_type=job_type,
            input_json={"concurrency": 3},
            created_by="test",
        )
        job_id = job.id
        work_queue = WorkQueue(session)
        for index in range(10):
            work_queue.enqueue(
                job_id=job_id,
                work_type="account.backfill_session",
                input_json={"index": index},
            )
        session.commit()

    def claim_once(worker_id: str) -> str:
        with session_factory() as session:
            work = WorkQueue(session).claim_next(worker_id=worker_id, job_id=job_id)
            session.commit()
            return work.id if work is not None else ""

    with ThreadPoolExecutor(max_workers=3) as executor:
        claimed_ids = list(executor.map(claim_once, [f"worker-{index}" for index in range(3)]))

    with session_factory() as session:
        works = session.scalars(select(WorkItemModel).where(WorkItemModel.job_id == job_id)).all()
        running = [work for work in works if work.work_status == "running"]

        assert all(claimed_ids)
        assert len(set(claimed_ids)) == 3
        assert len(running) == 3
        assert {work.claimed_by for work in running} == {"worker-0", "worker-1", "worker-2"}

        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def _skip_if_live_work_exists(session, *, job_type: str) -> None:
    live_work = session.scalars(
        select(WorkItemModel.id)
        .join(JobModel, JobModel.id == WorkItemModel.job_id)
        .where(
            WorkItemModel.work_status.in_(("queued", "running")),
            JobModel.type != job_type,
        )
        .limit(1)
    ).first()
    if live_work is not None:
        pytest.skip("shared database has live non-test work; run_one() would claim it")
