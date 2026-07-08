from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from socket import gethostname
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from refactor_app.application.jobs.queue import JobQueue, WorkQueue
from refactor_app.infrastructure.db.models import (
    JobModel,
    JobRunModel,
    SpaceCredentialModel,
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
    WorkItemModel,
)
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
            session.commit()

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
                input_json = {**job.input_json, "_job_id": job.id, "_run_id": run.id}
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

            run.output_json = output
            if _is_work_summary_output(output):
                summary = _summary_from_output(output)
                if summary["queued"] == 0 and summary["running"] == 0:
                    run.run_status = "failed" if summary["failed"] > 0 else "succeeded"
                    run.finished_at = datetime.now(UTC)
                    job.job_status = run.run_status
                    if run.run_status == "failed":
                        run.error_code = "work_failed"
                        run.error_message = (
                            f"failed={summary['failed']} queued={summary['queued']} "
                            f"running={summary['running']}"
                        )
                    else:
                        run.error_code = ""
                        run.error_message = ""
                else:
                    run.run_status = "running"
                    run.finished_at = None
                    job.job_status = "running"
            else:
                run.run_status = "succeeded"
                run.finished_at = datetime.now(UTC)
                job.job_status = "succeeded"
            job.updated_at = datetime.now(UTC)
            events.write(
                run_id=run.id,
                event_type=f"job.{run.run_status}",
                message=f"job {job.type} {run.run_status}",
                level="ERROR" if run.run_status == "failed" else "INFO",
            )
            session.commit()
            return job.id

    def run_one_work_for_job(self, job_id: str) -> str | None:
        return self._run_one_work(job_id=job_id)

    def run_claimed_work(self, work_id: str) -> str | None:
        return self._run_claimed_work(work_id)

    def _run_one_work(self, *, job_id: str = "") -> str | None:
        with self.session_factory() as session:
            work = WorkQueue(session).claim_next(worker_id=self.worker_id, job_id=job_id)
            if work is None:
                session.commit()
                return None

            work_id = work.id
            session.commit()
        return self._run_claimed_work(work_id)

    def _run_claimed_work(self, work_id: str) -> str | None:
        with self.session_factory() as session:
            work = session.get(WorkItemModel, work_id)
            if work is None:
                return None
            job_id_value = work.job_id
            work_type = work.work_type
            input_json = {**dict(work.input_json), "_work_id": work_id}
            work_context = _work_context(session, input_json)
            run_id = str(input_json.get("_run_id") or "")
            if run_id:
                EventWriter(session).write(
                    run_id=run_id,
                    event_type="work.started",
                    message=f"work {work_type} started",
                    data_json={"work_id": work_id, "work_type": work_type, **work_context},
                )
            session.commit()

            handler = self._work_handlers.get(work_type)
            if handler is None:
                work = session.get(WorkItemModel, work_id)
                if work is None:
                    return work_id
                _fail_work(
                    work,
                    error_code="unknown_work_type",
                    error_message=work.work_type,
                    output_json={**work_context, "error": "unknown_work_type"},
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
                            **work_context,
                            "error": "unknown_work_type",
                        },
                    )
                _finalize_parent_work_job(session, job_id=job_id_value, run_id=run_id)
                session.commit()
                return work_id

            try:
                output = handler(session, input_json) or {}
            except Exception as exc:
                work = session.get(WorkItemModel, work_id)
                if work is None:
                    return work_id
                failure_context = {
                    **work_context,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                _fail_work(
                    work,
                    error_code="handler_error",
                    error_message=f"{type(exc).__name__}: {exc}",
                    output_json=failure_context,
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
                            **work_context,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    )
                _finalize_parent_work_job(session, job_id=job_id_value, run_id=run_id)
                session.commit()
                return work_id

            now = datetime.now(UTC)
            work = session.get(WorkItemModel, work_id)
            if work is None:
                return work_id
            work.work_status = "succeeded"
            work.finished_at = now
            work.output_json = {**work_context, **output}
            work.error_code = ""
            work.error_message = ""
            work.updated_at = now
            if run_id:
                EventWriter(session).write(
                    run_id=run_id,
                    event_type="work.succeeded",
                    message=f"work {work_type} succeeded",
                    data_json={
                        "work_id": work_id,
                        "work_type": work_type,
                        **work_context,
                        "output": {**work_context, **output},
                    },
                )
            _finalize_parent_work_job(session, job_id=job_id_value, run_id=run_id)
            session.commit()
            return work_id


def _fail_work(
    work: WorkItemModel,
    *,
    error_code: str,
    error_message: str,
    output_json: dict | None = None,
) -> None:
    now = datetime.now(UTC)
    work.work_status = "failed"
    work.finished_at = now
    work.error_code = error_code
    work.error_message = error_message[:1000]
    if output_json is not None:
        work.output_json = {**dict(work.output_json or {}), **output_json}
    work.updated_at = now


def _is_work_summary_output(output: dict) -> bool:
    return all(key in output for key in ("queued", "running", "succeeded", "failed", "cancelled"))


def _summary_from_output(output: dict) -> dict[str, int]:
    summary: dict[str, int] = {}
    for key in ("queued", "running", "succeeded", "failed", "cancelled"):
        try:
            summary[key] = int(output.get(key) or 0)
        except (TypeError, ValueError):
            summary[key] = 0
    return summary


def _finalize_parent_work_job(session: Session, *, job_id: str, run_id: str = "") -> None:
    if not job_id:
        return
    summary = {
        "queued": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }
    rows = session.execute(
        select(WorkItemModel.work_status, func.count())
        .where(WorkItemModel.job_id == job_id)
        .group_by(WorkItemModel.work_status)
    ).all()
    for status, count in rows:
        if status in summary:
            summary[status] = int(count or 0)

    job = session.get(JobModel, job_id)
    run = session.get(JobRunModel, run_id) if run_id else None
    if run is None:
        run = session.scalars(
            select(JobRunModel)
            .where(JobRunModel.job_id == job_id)
            .order_by(JobRunModel.started_at.desc().nullslast())
            .limit(1)
        ).first()

    now = datetime.now(UTC)
    if job is not None:
        if summary["queued"] == 0 and summary["running"] == 0:
            job.job_status = "failed" if summary["failed"] > 0 else "succeeded"
        else:
            job.job_status = "running"
        job.updated_at = now
    if run is not None:
        run.output_json = summary
        if summary["queued"] == 0 and summary["running"] == 0:
            run.run_status = "failed" if summary["failed"] > 0 else "succeeded"
            run.finished_at = now
            if run.run_status == "failed":
                run.error_code = "work_failed"
                run.error_message = (
                    f"failed={summary['failed']} queued={summary['queued']} "
                    f"running={summary['running']}"
                )
            else:
                run.error_code = ""
                run.error_message = ""
        else:
            run.run_status = "running"
            run.finished_at = None


def _work_context(session: Session, input_json: dict) -> dict:
    user_account_id = str(input_json.get("user_account_id") or "")
    space_id = str(input_json.get("space_id") or "")
    space_membership_id = str(input_json.get("space_membership_id") or "")
    space_credential_id = str(input_json.get("space_credential_id") or "")
    downstream_channel_id = str(input_json.get("downstream_channel_id") or "")

    if space_membership_id:
        membership = session.get(SpaceMembershipModel, space_membership_id)
        if membership is not None:
            user_account_id = user_account_id or membership.user_account_id
            space_id = space_id or membership.space_id

    if space_credential_id:
        credential = session.get(SpaceCredentialModel, space_credential_id)
        if credential is not None:
            user_account_id = user_account_id or credential.user_account_id
            space_id = space_id or credential.space_id
            space_membership_id = space_membership_id or str(
                credential.space_membership_id or ""
            )

    account = session.get(UserAccountModel, user_account_id) if user_account_id else None
    space = session.get(SpaceModel, space_id) if space_id else None
    return {
        "user_account_id": user_account_id,
        "email": account.email if account is not None else "",
        "space_id": space_id,
        "external_space_id": space.external_space_id if space is not None else "",
        "space_name": space.name if space is not None else "",
        "credential_type": space.credential_type if space is not None else "",
        "space_membership_id": space_membership_id,
        "space_credential_id": space_credential_id,
        "downstream_channel_id": downstream_channel_id,
    }
