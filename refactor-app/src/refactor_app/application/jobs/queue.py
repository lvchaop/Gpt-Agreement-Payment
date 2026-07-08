from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.models import JobModel, WorkItemModel


JOB_WORK_COUNT_LIMITED_WORK_TYPES = {
    "account.backfill_session_rt",
    "account.backfill_session",
    "account.backfill_rt",
    "space.business_access_token.create.account",
    "space_credential.push.account",
    "space.recycle.binding",
    "account.protocol_register.one",
}

JOB_SCOPED_WORK_TYPES = {
    "space.membership_invite.account",
    "space.business_access_token.create.account",
    "space_credential.push.account",
    "space.recycle.binding",
    "account.protocol_register.one",
}
JOB_SCOPED_CLAIM_LIMIT = 350


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
        claim_limit = JOB_SCOPED_CLAIM_LIMIT if job_id else 100
        stmt = (
            select(WorkItemModel)
            .where(WorkItemModel.work_status == "queued")
            .order_by(WorkItemModel.priority.desc(), WorkItemModel.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(claim_limit)
        )
        if job_id:
            stmt = stmt.where(WorkItemModel.job_id == job_id)
        else:
            stmt = stmt.where(~WorkItemModel.work_type.in_(JOB_SCOPED_WORK_TYPES))
        work = None
        for candidate in self.session.scalars(stmt).all():
            if candidate.work_type in JOB_WORK_COUNT_LIMITED_WORK_TYPES and not self._can_claim_limited_job_work(candidate):
                continue
            work = candidate
            break
        if work is None and not job_id:
            work = self.session.scalars(
                select(WorkItemModel)
                .where(
                    WorkItemModel.work_status == "queued",
                    ~WorkItemModel.work_type.in_(JOB_WORK_COUNT_LIMITED_WORK_TYPES | JOB_SCOPED_WORK_TYPES),
                )
                .order_by(WorkItemModel.priority.desc(), WorkItemModel.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            ).first()
        if work is None:
            return None
        now = datetime.now(UTC)
        work.work_status = "running"
        work.claimed_by = worker_id
        work.claimed_at = now
        work.started_at = now
        work.updated_at = now
        return work

    def _can_claim_limited_job_work(self, candidate: WorkItemModel) -> bool:
        job = self.session.scalars(
            select(JobModel)
            .where(JobModel.id == candidate.job_id)
            .with_for_update()
            .limit(1)
        ).first()
        if job is None:
            return False
        try:
            work_count = int((job.input_json or {}).get("work_count") or 1)
        except (TypeError, ValueError):
            work_count = 1
        work_count = max(1, work_count)
        conditions = [
            WorkItemModel.job_id == candidate.job_id,
            WorkItemModel.work_status == "running",
            WorkItemModel.work_type == candidate.work_type,
        ]
        if candidate.work_type == "space.business_access_token.create.account":
            external_space_id = str((candidate.input_json or {}).get("external_space_id") or "")
            conditions.append(WorkItemModel.input_json["external_space_id"].astext == external_space_id)
        running_count = self.session.scalar(
            select(func.count()).select_from(WorkItemModel).where(*conditions)
        )
        return int(running_count or 0) < work_count
