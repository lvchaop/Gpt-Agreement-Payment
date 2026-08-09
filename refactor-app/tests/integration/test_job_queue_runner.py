from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from refactor_app.api.routes.jobs import cancel_job
from refactor_app.application.jobs.queue import (
    DEFAULT_WORK_LEASE_SECONDS,
    JobQueue,
    WorkQueue,
)
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


def test_all_at_once_claims_all_remaining_work_after_partial_completion() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    job_type = "test.all-at-once-partially-completed"

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
            priority=2_147_483_647,
        )
        job.job_status = "running"
        queue = WorkQueue(session)
        works = [
            queue.enqueue(job_id=job.id, work_type="test.atomic.remaining", input_json={"i": i})
            for i in range(3)
        ]
        session.flush()
        works[0].work_status = "succeeded"
        works[0].finished_at = datetime.now(UTC)
        job_id = job.id
        succeeded_work_id = works[0].id
        remaining_work_ids = {works[1].id, works[2].id}
        session.commit()

    with session_factory() as session:
        claimed, blocks_normal = WorkQueue(session).claim_all_at_once_available(
            worker_id="worker-partial-atomic",
            limit=1,
        )
        assert claimed == []
        assert blocks_normal is True
        session.commit()

    with session_factory() as session:
        claimed, blocks_normal = WorkQueue(session).claim_all_at_once_available(
            worker_id="worker-partial-atomic",
            limit=2,
        )
        assert {work.id for work in claimed} == remaining_work_ids
        assert blocks_normal is True
        session.commit()

    with session_factory() as session:
        succeeded = session.get(WorkItemModel, succeeded_work_id)
        remaining = session.scalars(
            select(WorkItemModel).where(WorkItemModel.id.in_(remaining_work_ids))
        ).all()
        assert succeeded is not None
        assert succeeded.work_status == "succeeded"
        assert succeeded.claimed_by == ""
        assert {work.work_status for work in remaining} == {"running"}
        assert {work.claimed_by for work in remaining} == {"worker-partial-atomic"}
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


def test_default_work_lease_recovers_without_fifteen_minute_stall() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    job_type = "test.default-work-lease"

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
            work_type="test.default-work-lease.one",
            input_json={},
        )
        job_id = job.id
        work_id = work.id
        session.commit()

    before = datetime.now(UTC)
    with session_factory() as session:
        claimed = WorkQueue(session).claim_available(worker_id="lease-worker", limit=1)
        assert [row.id for row in claimed] == [work_id]
        session.commit()
    after = datetime.now(UTC)

    with session_factory() as session:
        saved = session.get(WorkItemModel, work_id)
        assert saved is not None
        assert DEFAULT_WORK_LEASE_SECONDS == 120
        assert before + timedelta(seconds=120) <= saved.lease_expires_at
        assert saved.lease_expires_at <= after + timedelta(seconds=120)
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_release_claimed_requeues_only_selected_work_owned_by_worker() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    job_type = "test.release-owned-work"
    claimed_at = datetime.now(UTC) - timedelta(minutes=1)
    released_at = datetime.now(UTC)

    with session_factory() as session:
        session.execute(
            delete(WorkItemModel).where(
                WorkItemModel.job_id.in_(select(JobModel.id).where(JobModel.type == job_type))
            )
        )
        session.execute(delete(JobModel).where(JobModel.type == job_type))
        job = JobQueue(session).enqueue(
            job_type=job_type,
            input_json={"work_count": 4},
            created_by="test",
        )
        job.job_status = "running"
        queue = WorkQueue(session)
        works = [
            queue.enqueue(job_id=job.id, work_type="test.release.one", input_json={})
            for _ in range(4)
        ]
        session.flush()
        for work in works[:3]:
            work.work_status = "running"
            work.claimed_at = claimed_at
            work.started_at = claimed_at
            work.lease_expires_at = claimed_at + timedelta(minutes=15)
        works[0].claimed_by = "worker-a"
        works[1].claimed_by = "worker-a"
        works[2].claimed_by = "worker-b"
        works[3].work_status = "succeeded"
        works[3].claimed_by = "worker-a"
        works[3].finished_at = claimed_at
        job_id = job.id
        work_ids = [work.id for work in works]
        session.commit()

    with session_factory() as session:
        assert (
            WorkQueue(session).release_claimed(
                worker_id="worker-a",
                work_ids=[work_ids[0], work_ids[2], work_ids[3]],
                now=released_at,
            )
            == 1
        )
        session.commit()

    with session_factory() as session:
        released, unselected, foreign, completed = [
            session.get(WorkItemModel, work_id) for work_id in work_ids
        ]
        assert released.work_status == "queued"
        assert released.claimed_by == ""
        assert released.claimed_at is None
        assert released.started_at is None
        assert released.lease_expires_at is None
        assert released.updated_at == released_at
        assert unselected.work_status == "running"
        assert unselected.claimed_by == "worker-a"
        assert foreign.work_status == "running"
        assert foreign.claimed_by == "worker-b"
        assert completed.work_status == "succeeded"
        assert completed.claimed_by == "worker-a"
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_runner_release_claimed_work_commits_all_owned_claims() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    runner = JobRunner(session_factory)
    job_type = "test.runner-release-owned-work"
    claimed_at = datetime.now(UTC) - timedelta(minutes=1)

    with session_factory() as session:
        session.execute(
            delete(WorkItemModel).where(
                WorkItemModel.job_id.in_(select(JobModel.id).where(JobModel.type == job_type))
            )
        )
        session.execute(delete(JobModel).where(JobModel.type == job_type))
        job = JobQueue(session).enqueue(
            job_type=job_type,
            input_json={"work_count": 3},
            created_by="test",
        )
        job.job_status = "running"
        queue = WorkQueue(session)
        works = [
            queue.enqueue(job_id=job.id, work_type="test.runner-release.one", input_json={})
            for _ in range(3)
        ]
        session.flush()
        for work in works:
            work.work_status = "running"
            work.claimed_at = claimed_at
            work.started_at = claimed_at
            work.lease_expires_at = claimed_at + timedelta(minutes=15)
        works[0].claimed_by = runner.worker_id
        works[1].claimed_by = runner.worker_id
        works[2].claimed_by = "another-worker"
        job_id = job.id
        work_ids = [work.id for work in works]
        session.commit()

    assert runner.release_claimed_work() == 2

    with session_factory() as session:
        first, second, foreign = [session.get(WorkItemModel, work_id) for work_id in work_ids]
        assert {first.work_status, second.work_status} == {"queued"}
        assert first.claimed_by == second.claimed_by == ""
        assert foreign.work_status == "running"
        assert foreign.claimed_by == "another-worker"
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_release_claimed_rejects_a_stale_claim_generation() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    job_type = "test.release-claim-generation"
    stale_claimed_at = datetime(2001, 1, 1, tzinfo=UTC)
    current_claimed_at = datetime(2001, 1, 2, tzinfo=UTC)
    current_lease_expires_at = current_claimed_at + timedelta(seconds=120)
    released_at = datetime(2001, 1, 3, tzinfo=UTC)

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
            work_type="test.release-claim-generation.one",
            input_json={},
        )
        session.flush()
        worker_id = f"generation-worker-{job.id}"
        work.work_status = "running"
        work.claimed_by = worker_id
        work.claimed_at = current_claimed_at
        work.started_at = current_claimed_at
        work.lease_expires_at = current_lease_expires_at
        job_id = job.id
        work_id = work.id
        session.commit()

    with session_factory() as session:
        assert (
            WorkQueue(session).release_claimed(
                worker_id=worker_id,
                claim_generations={work_id: stale_claimed_at},
                now=released_at,
            )
            == 0
        )
        session.commit()

    with session_factory() as session:
        saved = session.get(WorkItemModel, work_id)
        assert saved is not None
        assert saved.work_status == "running"
        assert saved.claimed_by == worker_id
        assert saved.claimed_at == current_claimed_at
        assert saved.started_at == current_claimed_at
        assert saved.lease_expires_at == current_lease_expires_at

    with session_factory() as session:
        assert (
            WorkQueue(session).release_claimed(
                worker_id=worker_id,
                claim_generations={work_id: current_claimed_at},
                now=released_at,
            )
            == 1
        )
        session.commit()

    with session_factory() as session:
        saved = session.get(WorkItemModel, work_id)
        assert saved is not None
        assert saved.work_status == "queued"
        assert saved.claimed_by == ""
        assert saved.claimed_at is None
        assert saved.started_at is None
        assert saved.lease_expires_at is None
        assert saved.updated_at == released_at
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_expire_claimed_only_expires_owned_work_before_immediate_requeue() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    job_type = "test.expire-owned-work"
    expired_at = datetime(1980, 1, 2, tzinfo=UTC)
    owned_claimed_at = datetime(1980, 1, 1, tzinfo=UTC)
    foreign_claimed_at = datetime(1980, 1, 1, 1, tzinfo=UTC)
    owned_initial_lease = expired_at + timedelta(minutes=2)
    foreign_initial_lease = expired_at + timedelta(minutes=3)

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
        queue = WorkQueue(session)
        owned = queue.enqueue(job_id=job.id, work_type="test.expire.one", input_json={})
        foreign = queue.enqueue(job_id=job.id, work_type="test.expire.one", input_json={})
        session.flush()
        worker_id = f"expire-worker-{job.id}"
        foreign_worker_id = f"foreign-worker-{job.id}"
        owned.work_status = "running"
        owned.claimed_by = worker_id
        owned.claimed_at = owned_claimed_at
        owned.started_at = owned_claimed_at
        owned.lease_expires_at = owned_initial_lease
        foreign.work_status = "running"
        foreign.claimed_by = foreign_worker_id
        foreign.claimed_at = foreign_claimed_at
        foreign.started_at = foreign_claimed_at
        foreign.lease_expires_at = foreign_initial_lease
        job_id = job.id
        owned_work_id = owned.id
        foreign_work_id = foreign.id
        session.commit()

    with session_factory() as session:
        assert WorkQueue(session).expire_claimed(worker_id=worker_id, now=expired_at) == 1
        session.commit()

    with session_factory() as session:
        owned = session.get(WorkItemModel, owned_work_id)
        foreign = session.get(WorkItemModel, foreign_work_id)
        assert owned is not None
        assert foreign is not None
        assert owned.work_status == "running"
        assert owned.claimed_by == worker_id
        assert owned.claimed_at == owned_claimed_at
        assert owned.started_at == owned_claimed_at
        assert owned.lease_expires_at == expired_at - timedelta(microseconds=1)
        assert owned.updated_at == expired_at
        assert foreign.work_status == "running"
        assert foreign.claimed_by == foreign_worker_id
        assert foreign.claimed_at == foreign_claimed_at
        assert foreign.started_at == foreign_claimed_at
        assert foreign.lease_expires_at == foreign_initial_lease

    with session_factory() as session:
        assert WorkQueue(session).requeue_expired(now=expired_at) == 1
        session.commit()

    with session_factory() as session:
        owned = session.get(WorkItemModel, owned_work_id)
        foreign = session.get(WorkItemModel, foreign_work_id)
        assert owned is not None
        assert foreign is not None
        assert owned.work_status == "queued"
        assert owned.claimed_by == ""
        assert owned.claimed_at is None
        assert owned.started_at is None
        assert owned.lease_expires_at is None
        assert foreign.work_status == "running"
        assert foreign.claimed_by == foreign_worker_id
        assert foreign.claimed_at == foreign_claimed_at
        assert foreign.lease_expires_at == foreign_initial_lease
        session.execute(delete(WorkItemModel).where(WorkItemModel.job_id == job_id))
        session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.commit()


def test_stale_handler_cannot_overwrite_a_new_claim_generation() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    runner = JobRunner(session_factory)
    job_type = "test.claim-generation-fence"
    work_type = "test.claim-generation-fence.one"
    first_claimed_at = datetime.now(UTC) - timedelta(minutes=1)
    second_claimed_at = datetime.now(UTC)

    def replace_claim(session, input_json):
        saved = session.get(WorkItemModel, input_json["_work_id"])
        saved.claimed_at = second_claimed_at
        saved.lease_expires_at = second_claimed_at + timedelta(seconds=120)
        session.commit()
        return {"stale_result": True}

    runner.register_work(work_type, replace_claim)
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
        work = WorkQueue(session).enqueue(job_id=job.id, work_type=work_type, input_json={})
        session.flush()
        work.work_status = "running"
        work.claimed_by = runner.worker_id
        work.claimed_at = first_claimed_at
        work.started_at = first_claimed_at
        work.lease_expires_at = first_claimed_at + timedelta(seconds=120)
        job_id = job.id
        work_id = work.id
        session.commit()

    assert runner.run_claimed_work(work_id) == work_id

    with session_factory() as session:
        saved = session.get(WorkItemModel, work_id)
        assert saved.work_status == "running"
        assert saved.claimed_at == second_claimed_at
        assert saved.output_json == {}
        assert session.get(JobModel, job_id).job_status == "running"
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
