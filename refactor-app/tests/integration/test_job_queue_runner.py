from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from refactor_app.api.routes.jobs import cancel_job
from refactor_app.application.jobs.queue import JobQueue, WorkQueue
from refactor_app.application.jobs.runner import JobRunner
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    JobEventModel,
    JobModel,
    JobRunModel,
    UserAccountModel,
    WorkItemModel,
)


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
        events = session.scalars(
            select(JobEventModel).where(JobEventModel.run_id == runs[0].id)
        ).all()

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


def test_work_claim_locks_only_available_job_slots() -> None:
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
            input_json={"work_count": 3},
            created_by="test",
        )
        job.job_status = "running"
        job_id = job.id
        work_queue = WorkQueue(session)
        for index in range(10):
            work_queue.enqueue(
                job_id=job_id,
                work_type="account.protocol_register.one",
                input_json={"index": index},
            )
        session.commit()

    with session_factory() as session:
        claimed = WorkQueue(session).claim_available(
            worker_id="worker-batch",
            job_id=job_id,
            limit=100,
        )
        claimed_ids = [work.id for work in claimed]
        session.commit()

    with session_factory() as session:
        works = session.scalars(select(WorkItemModel).where(WorkItemModel.job_id == job_id)).all()
        running = [work for work in works if work.work_status == "running"]

        assert all(claimed_ids)
        assert len(set(claimed_ids)) == 3
        assert len(running) == 3
        assert {work.claimed_by for work in running} == {"worker-batch"}
        assert len([work for work in works if work.work_status == "queued"]) == 7

        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_all_at_once_work_is_never_claimed_partially() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    job_type = "test.all-at-once-claim"

    with session_factory() as session:
        session.execute(
            delete(WorkItemModel).where(
                WorkItemModel.job_id.in_(select(JobModel.id).where(JobModel.type == job_type))
            )
        )
        session.execute(delete(JobModel).where(JobModel.type == job_type))
        job = JobQueue(session).enqueue(
            job_type=job_type,
            input_json={
                "work_count": 3,
                "dispatch_mode": "all_at_once",
                "required_slots": 3,
            },
            created_by="test",
        )
        job.job_status = "running"
        job_id = job.id
        queue = WorkQueue(session)
        for index in range(3):
            queue.enqueue(job_id=job_id, work_type="test.atomic", input_json={"index": index})
        session.commit()

    with session_factory() as session:
        claimed, blocks_normal = WorkQueue(session).claim_all_at_once_available(
            worker_id="worker-atomic",
            limit=2,
        )
        assert claimed == []
        assert blocks_normal is True
        assert (
            WorkQueue(session).claim_available(
                worker_id="worker-normal",
                job_id=job_id,
                limit=10,
            )
            == []
        )
        session.commit()

    with session_factory() as session:
        claimed, blocks_normal = WorkQueue(session).claim_all_at_once_available(
            worker_id="worker-atomic",
            limit=3,
        )
        assert len(claimed) == 3
        assert blocks_normal is True
        session.commit()

    with session_factory() as session:
        works = session.scalars(select(WorkItemModel).where(WorkItemModel.job_id == job_id)).all()
        assert {work.work_status for work in works} == {"running"}
        assert {work.claimed_by for work in works} == {"worker-atomic"}
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_work_count_is_job_wide_and_execution_key_is_mutually_exclusive() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    job_type = "test.authorize-per-space"

    with session_factory() as session:
        session.execute(
            delete(WorkItemModel).where(
                WorkItemModel.job_id.in_(select(JobModel.id).where(JobModel.type == job_type))
            )
        )
        session.execute(delete(JobModel).where(JobModel.type == job_type))
        job = JobQueue(session).enqueue(
            job_type=job_type,
            input_json={"work_count": 2},
            created_by="test",
        )
        job.job_status = "running"
        job_id = job.id
        work_queue = WorkQueue(session)
        for index in range(3):
            work_queue.enqueue(
                job_id=job_id,
                work_type="space.business_access_token.create.account",
                execution_key="space:space-a",
                input_json={"external_space_id": "space-a", "index": index},
            )
        for index in range(2):
            work_queue.enqueue(
                job_id=job_id,
                work_type="space.business_access_token.create.account",
                execution_key="space:space-b",
                input_json={"external_space_id": "space-b", "index": index},
            )
        session.commit()

    with session_factory() as session:
        claimed = WorkQueue(session).claim_available(
            worker_id="worker-batch",
            job_id=job_id,
            limit=5,
        )
        claimed_ids = [work.id for work in claimed]
        session.commit()

    with session_factory() as session:
        works = session.scalars(select(WorkItemModel).where(WorkItemModel.job_id == job_id)).all()
        running = [work for work in works if work.work_status == "running"]
        running_by_space: dict[str, int] = {}
        for work in running:
            external_space_id = str((work.input_json or {}).get("external_space_id") or "")
            running_by_space[external_space_id] = running_by_space.get(external_space_id, 0) + 1

        assert len(claimed_ids) == 2
        assert running_by_space == {"space-a": 1, "space-b": 1}

        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_expired_work_lease_is_requeued() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    job_type = "test.expired-work-lease"

    with session_factory() as session:
        session.execute(
            delete(WorkItemModel).where(
                WorkItemModel.job_id.in_(select(JobModel.id).where(JobModel.type == job_type))
            )
        )
        session.execute(delete(JobModel).where(JobModel.type == job_type))
        job = JobQueue(session).enqueue(
            job_type=job_type,
            input_json={"work_count": 1},
            created_by="test",
        )
        job.job_status = "running"
        work = WorkQueue(session).enqueue(
            job_id=job.id,
            work_type="account.protocol_register.one",
            input_json={},
        )
        session.flush()
        work.work_status = "running"
        work.claimed_by = "dead-worker"
        work.claimed_at = datetime.now(UTC) - timedelta(minutes=20)
        work.lease_expires_at = datetime.now(UTC) - timedelta(minutes=5)
        work.started_at = work.claimed_at
        job_id = job.id
        work_id = work.id
        session.commit()

    with session_factory() as session:
        assert WorkQueue(session).requeue_expired() == 1
        session.commit()

    with session_factory() as session:
        work = session.get(WorkItemModel, work_id)
        assert work is not None
        assert work.work_status == "queued"
        assert work.claimed_by == ""
        assert work.lease_expires_at is None
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_last_work_completion_finalizes_parent_job() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    job_type = "test.last-work-finalizes-job"
    work_type = "test.last-work"
    runner = JobRunner(session_factory)
    runner.register_work(work_type, lambda _session, _input: {"ok": True})

    with session_factory() as session:
        session.execute(
            delete(WorkItemModel).where(
                WorkItemModel.job_id.in_(select(JobModel.id).where(JobModel.type == job_type))
            )
        )
        session.execute(
            delete(JobRunModel).where(
                JobRunModel.job_id.in_(select(JobModel.id).where(JobModel.type == job_type))
            )
        )
        session.execute(delete(JobModel).where(JobModel.type == job_type))
        now = datetime.now(UTC)
        job = JobQueue(session).enqueue(
            job_type=job_type,
            input_json={"work_count": 1},
            created_by="test",
        )
        job.job_status = "running"
        run = JobRunModel(
            id="test-last-work-run",
            job_id=job.id,
            run_status="running",
            attempt=1,
            started_at=now,
            output_json={},
        )
        session.add(run)
        work = WorkQueue(session).enqueue(
            job_id=job.id,
            work_type=work_type,
            input_json={"_run_id": run.id},
        )
        session.flush()
        work.work_status = "running"
        work.claimed_by = runner.worker_id
        work.claimed_at = now
        work.lease_expires_at = now + timedelta(minutes=15)
        work.started_at = now
        job_id = job.id
        work_id = work.id
        session.commit()

    assert runner.run_claimed_work(work_id) == work_id

    with session_factory() as session:
        assert session.get(JobModel, job_id).job_status == "succeeded"
        assert session.get(JobRunModel, "test-last-work-run").run_status == "succeeded"
        assert session.get(WorkItemModel, work_id).work_status == "succeeded"
        session.execute(delete(JobEventModel).where(JobEventModel.run_id == "test-last-work-run"))
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobRunModel).where(JobRunModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_skipped_work_is_persisted_and_counted_separately() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    job_type = "test.skipped-work-finalizes-job"
    work_type = "test.skipped-work"
    runner = JobRunner(session_factory)
    runner.register_work(
        work_type,
        lambda _session, _input: {
            "_work_outcome": "skipped",
            "skip_reason": "snapshot is not ready",
        },
    )

    with session_factory() as session:
        now = datetime.now(UTC)
        job = JobQueue(session).enqueue(
            job_type=job_type,
            input_json={"work_count": 1},
            created_by="test",
        )
        job.job_status = "running"
        run = JobRunModel(
            id=f"test-skipped-work-run-{job.id}",
            job_id=job.id,
            run_status="running",
            attempt=1,
            started_at=now,
            output_json={},
        )
        session.add(run)
        work = WorkQueue(session).enqueue(
            job_id=job.id,
            work_type=work_type,
            input_json={"_run_id": run.id},
        )
        session.flush()
        work.work_status = "running"
        work.claimed_by = runner.worker_id
        work.claimed_at = now
        work.lease_expires_at = now + timedelta(minutes=15)
        work.started_at = now
        job_id = job.id
        run_id = run.id
        work_id = work.id
        session.commit()

    assert runner.run_claimed_work(work_id) == work_id

    with session_factory() as session:
        saved_work = session.get(WorkItemModel, work_id)
        saved_run = session.get(JobRunModel, run_id)
        assert saved_work.work_status == "skipped"
        assert saved_work.error_code == "work_skipped"
        assert session.get(JobModel, job_id).job_status == "succeeded"
        assert saved_run.run_status == "succeeded"
        assert saved_run.output_json["skipped"] == 1
        event_types = set(
            session.scalars(
                select(JobEventModel.event_type).where(JobEventModel.run_id == run_id)
            ).all()
        )
        assert "work.skipped" in event_types
        session.execute(delete(JobEventModel).where(JobEventModel.run_id == run_id))
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobRunModel).where(JobRunModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_running_job_cancel_stops_queued_work_and_preserves_inflight_work() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    job_type = "test.cancel-running-job"

    with session_factory() as session:
        session.execute(
            delete(WorkItemModel).where(
                WorkItemModel.job_id.in_(select(JobModel.id).where(JobModel.type == job_type))
            )
        )
        session.execute(
            delete(JobRunModel).where(
                JobRunModel.job_id.in_(select(JobModel.id).where(JobModel.type == job_type))
            )
        )
        session.execute(delete(JobModel).where(JobModel.type == job_type))
        now = datetime.now(UTC)
        job = JobQueue(session).enqueue(
            job_type=job_type,
            input_json={"work_count": 1},
            created_by="test",
        )
        job.job_status = "running"
        run = JobRunModel(
            id="test-cancel-running-run",
            job_id=job.id,
            run_status="running",
            attempt=1,
            started_at=now,
            output_json={},
        )
        session.add(run)
        running_work = WorkQueue(session).enqueue(
            job_id=job.id,
            work_type="account.protocol_register.one",
            input_json={"_run_id": run.id},
        )
        queued_work = WorkQueue(session).enqueue(
            job_id=job.id,
            work_type="account.protocol_register.one",
            input_json={"_run_id": run.id},
        )
        session.flush()
        running_work.work_status = "running"
        running_work.claimed_by = "worker-test"
        running_work.claimed_at = now
        running_work.lease_expires_at = now + timedelta(minutes=15)
        running_work.started_at = now
        job_id = job.id
        running_work_id = running_work.id
        queued_work_id = queued_work.id
        session.commit()

    with session_factory() as session:
        result = cancel_job(job_id, session)
        assert result["job_status"] == "cancelled"
        assert result["cancelled_work_count"] == 1
        assert result["running_work_count"] == 1

    with session_factory() as session:
        assert session.get(JobModel, job_id).job_status == "cancelled"
        assert session.get(JobRunModel, "test-cancel-running-run").run_status == "cancelled"
        assert session.get(WorkItemModel, queued_work_id).work_status == "cancelled"
        assert session.get(WorkItemModel, running_work_id).work_status == "running"
        session.execute(
            delete(JobEventModel).where(JobEventModel.run_id == "test-cancel-running-run")
        )
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobRunModel).where(JobRunModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_protocol_registration_cancel_deletes_registering_placeholder() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    now = datetime.now(UTC)

    with session_factory() as session:
        job = JobQueue(session).enqueue(
            job_type="account.protocol_register",
            input_json={"work_count": 1},
            created_by="test",
        )
        job.job_status = "running"
        run = JobRunModel(
            id=f"test-cancel-protocol-run-{job.id}",
            job_id=job.id,
            run_status="running",
            attempt=1,
            started_at=now,
            output_json={},
        )
        session.add(run)
        placeholder = UserAccountModel(
            id=f"test-registering-placeholder-{job.id}",
            email="",
            account_status="registering",
            session_status="unknown",
            created_at=now,
            updated_at=now,
        )
        session.add(placeholder)
        work = WorkQueue(session).enqueue(
            job_id=job.id,
            work_type="account.protocol_register.one",
            input_json={"_run_id": run.id},
        )
        session.flush()
        work.work_status = "running"
        work.output_json = {"user_account_id": placeholder.id}
        work.claimed_by = "worker-test"
        work.claimed_at = now
        work.lease_expires_at = now + timedelta(minutes=15)
        work.started_at = now
        job_id = job.id
        run_id = run.id
        work_id = work.id
        placeholder_id = placeholder.id
        session.commit()

    with session_factory() as session:
        result = cancel_job(job_id, session)
        assert result["deleted_placeholder_count"] == 1

    with session_factory() as session:
        assert session.get(UserAccountModel, placeholder_id) is None
        session.execute(delete(JobEventModel).where(JobEventModel.run_id == run_id))
        session.execute(delete(WorkItemModel).where(WorkItemModel.id == work_id))
        session.execute(delete(JobRunModel).where(JobRunModel.id == run_id))
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
