from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.models import JobModel, WorkItemModel


class JobQueue:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self,
        *,
        job_type: str,
        input_json: dict,
        created_by: str = "",
        priority: int = 0,
    ) -> JobModel:
        now = datetime.now(UTC)
        job = JobModel(
            id=str(uuid4()),
            type=job_type,
            job_status="queued",
            priority=priority,
            input_json=input_json,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.session.add(job)
        return job

    def claim_next(self) -> JobModel | None:
        stmt = (
            select(JobModel)
            .where(JobModel.job_status == "queued")
            .order_by(JobModel.priority.desc(), JobModel.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = self.session.scalars(stmt).first()
        if job is None:
            return None
        job.job_status = "running"
        job.updated_at = datetime.now(UTC)
        return job


class WorkQueue:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self,
        *,
        job_id: str,
        work_type: str,
        input_json: dict,
        priority: int = 0,
    ) -> WorkItemModel:
        now = datetime.now(UTC)
        work = WorkItemModel(
            id=str(uuid4()),
            job_id=job_id,
            work_type=work_type,
            work_status="queued",
            priority=priority,
            input_json=input_json,
            output_json={},
            created_at=now,
            updated_at=now,
        )
        self.session.add(work)
        return work

    def claim_next(self, *, worker_id: str, job_id: str = "") -> WorkItemModel | None:
        stmt = (
            select(WorkItemModel)
            .where(WorkItemModel.work_status == "queued")
            .order_by(WorkItemModel.priority.desc(), WorkItemModel.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job_id:
            stmt = stmt.where(WorkItemModel.job_id == job_id)
        work = self.session.scalars(stmt).first()
        if work is None:
            return None
        now = datetime.now(UTC)
        work.work_status = "running"
        work.claimed_by = worker_id
        work.claimed_at = now
        work.started_at = now
        work.updated_at = now
        return work
