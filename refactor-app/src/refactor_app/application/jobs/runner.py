from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from socket import gethostname
from uuid import uuid4

from sqlalchemy.orm import Session

from refactor_app.application.jobs.queue import JobQueue, WorkQueue
from refactor_app.infrastructure.db.models import JobRunModel, WorkItemModel
from refactor_app.infrastructure.logging.event_writer import EventWriter

JobHandler = Callable[[Session, dict], dict | None]
WorkHandler = Callable[[Session, dict], dict | None]


class JobRunner:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory
        self._handlers: dict[str, JobHandler] = {}
        self._work_handlers: dict[str, WorkHandler] = {}
        self.worker_id = f"{gethostname()}-{uuid4()}"

    def register(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    def register_work(self, work_type: str, handler: WorkHandler) -> None:
        self._work_handlers[work_type] = handler

    def run_one(self) -> str | None:
        work_id = self._run_one_work()
        if work_id is not None:
            return work_id
        with self.session_factory() as session:
            queue = JobQueue(session)
            job = queue.claim_next()
            if job is None:
                session.commit()
                return None

            now = datetime.now(UTC)
            run = JobRunModel(
                id=str(uuid4()),
                job_id=job.id,
                run_status="running",
                attempt=1,
                started_at=now,
                output_json={},
            )
            session.add(run)
            session.flush()
            events = EventWriter(session)
            events.write(run_id=run.id, event_type="job.started", message=f"job {job.type} started")

            handler = self._handlers.get(job.type)
            if handler is None:
                run.run_status = "failed"
                run.finished_at = datetime.now(UTC)
                run.error_code = "unknown_job_type"
                run.error_message = job.type
                job.job_status = "failed"
                job.updated_at = datetime.now(UTC)
                events.write(
                    run_id=run.id,
                    event_type="job.failed",
                    message="unknown job type",
                    level="ERROR",
                    data_json={"job_type": job.type},
                )
                session.commit()
                return job.id

            try:
                input_json = {**job.input_json, "_job_id": job.id}
                output = handler(session, input_json) or {}
            except Exception as exc:
                run.run_status = "failed"
                run.finished_at = datetime.now(UTC)
                run.error_code = "handler_error"
                run.error_message = f"{type(exc).__name__}: {exc}"
                job.job_status = "failed"
                job.updated_at = datetime.now(UTC)
                events.write(
                    run_id=run.id,
                    event_type="job.failed",
                    message="handler error",
                    level="ERROR",
                    data_json={"error": run.error_message},
                )
                session.commit()
                return job.id

            run.run_status = "succeeded"
            run.finished_at = datetime.now(UTC)
            run.output_json = output
            job.job_status = "succeeded"
            job.updated_at = datetime.now(UTC)
            events.write(
                run_id=run.id,
                event_type="job.succeeded",
                message=f"job {job.type} succeeded",
            )
            session.commit()
            return job.id

    def run_one_work_for_job(self, job_id: str) -> str | None:
        return self._run_one_work(job_id=job_id)

    def _run_one_work(self, *, job_id: str = "") -> str | None:
        with self.session_factory() as session:
            work = WorkQueue(session).claim_next(worker_id=self.worker_id, job_id=job_id)
            if work is None:
                session.commit()
                return None

            work_id = work.id
            work_type = work.work_type
            input_json = {**dict(work.input_json), "_work_id": work_id}
            run_id = str(input_json.get("_run_id") or "")
            if run_id:
                EventWriter(session).write(
                    run_id=run_id,
                    event_type="work.started",
                    message=f"work {work_type} started",
                    data_json={"work_id": work_id, "work_type": work_type},
                )
            session.commit()

            handler = self._work_handlers.get(work_type)
            if handler is None:
                work = session.get(WorkItemModel, work_id)
                if work is None:
                    return work_id
                _fail_work(work, error_code="unknown_work_type", error_message=work.work_type)
                session.commit()
                return work_id

            try:
                output = handler(session, input_json) or {}
            except Exception as exc:
                work = session.get(WorkItemModel, work_id)
                if work is None:
                    return work_id
                _fail_work(
                    work,
                    error_code="handler_error",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                if run_id:
                    EventWriter(session).write(
                        run_id=run_id,
                        event_type="work.failed",
                        message=f"work {work_type} failed",
                        level="ERROR",
                        data_json={
                            "work_id": work_id,
                            "work_type": work_type,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    )
                session.commit()
                return work_id

            now = datetime.now(UTC)
            work = session.get(WorkItemModel, work_id)
            if work is None:
                return work_id
            work.work_status = "succeeded"
            work.finished_at = now
            work.output_json = output
            work.error_code = ""
            work.error_message = ""
            work.updated_at = now
            if run_id:
                EventWriter(session).write(
                    run_id=run_id,
                    event_type="work.succeeded",
                    message=f"work {work_type} succeeded",
                    data_json={"work_id": work_id, "work_type": work_type, "output": output},
                )
            session.commit()
            return work_id


def _fail_work(work: WorkItemModel, *, error_code: str, error_message: str) -> None:
    now = datetime.now(UTC)
    work.work_status = "failed"
    work.finished_at = now
    work.error_code = error_code
    work.error_message = error_message[:1000]
    work.updated_at = now
