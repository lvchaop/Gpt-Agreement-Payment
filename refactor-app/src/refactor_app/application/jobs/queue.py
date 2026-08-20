from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Integer, cast, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from refactor_app.infrastructure.db.models import JobModel, WorkItemModel

DEFAULT_WORK_LEASE_SECONDS = 120
PERSONAL_PAYPAL_LINK_TICK_JOB_TYPE = "space.personal_paypal_link.tick"
PERSONAL_PAYPAL_LINK_WORK_TYPE = "space.personal_paypal_link.space"


def normalize_personal_paypal_link_input(
    work_type: str,
    input_json: dict,
) -> dict:
    normalized_input_json = dict(input_json)
    if work_type in {
        PERSONAL_PAYPAL_LINK_TICK_JOB_TYPE,
        PERSONAL_PAYPAL_LINK_WORK_TYPE,
    }:
        normalized_input_json["checkout_attempt_mode"] = "new"
    return normalized_input_json


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
        normalized_input_json = normalize_personal_paypal_link_input(job_type, input_json)
        job = JobModel(
            id=str(uuid4()),
            type=job_type,
            job_status="queued",
            priority=priority,
            input_json=normalized_input_json,
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
        execution_key: str = "",
    ) -> WorkItemModel:
        now = datetime.now(UTC)
        normalized_input_json = normalize_personal_paypal_link_input(work_type, input_json)
        work = WorkItemModel(
            id=str(uuid4()),
            job_id=job_id,
            work_type=work_type,
            work_status="queued",
            priority=priority,
            execution_key=execution_key.strip(),
            input_json=normalized_input_json,
            output_json={},
            created_at=now,
            updated_at=now,
        )
        self.session.add(work)
        return work

    def claim_next(
        self,
        *,
        worker_id: str,
        job_id: str = "",
        lease_seconds: int = DEFAULT_WORK_LEASE_SECONDS,
    ) -> WorkItemModel | None:
        rows = self.claim_available(
            worker_id=worker_id,
            limit=1,
            job_id=job_id,
            lease_seconds=lease_seconds,
        )
        return rows[0] if rows else None

    def claim_available(
        self,
        *,
        worker_id: str,
        limit: int,
        job_id: str = "",
        lease_seconds: int = DEFAULT_WORK_LEASE_SECONDS,
    ) -> list[WorkItemModel]:
        requested = max(1, int(limit or 1))
        job = self._lock_next_eligible_job(job_id=job_id)
        if job is None:
            return []

        work_count = _job_work_count(job)
        running_count = int(
            self.session.scalar(
                select(func.count())
                .select_from(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job.id,
                    WorkItemModel.work_status == "running",
                )
            )
            or 0
        )
        available_slots = min(requested, max(0, work_count - running_count))
        if available_slots <= 0:
            return []

        rows = self._lock_queued_work(job_id=job.id, limit=available_slots)
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=max(30, int(lease_seconds or 0)))
        for work in rows:
            work.work_status = "running"
            work.claimed_by = worker_id
            work.claimed_at = now
            work.lease_expires_at = lease_expires_at
            work.started_at = now
            work.updated_at = now
        return rows

    def claim_all_at_once_available(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int = DEFAULT_WORK_LEASE_SECONDS,
    ) -> tuple[list[WorkItemModel], bool]:
        """Claim one all-at-once Job only when every required slot is available."""
        job = self._lock_next_all_at_once_job()
        if job is None:
            return [], False

        running_count = int(
            self.session.scalar(
                select(func.count())
                .select_from(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job.id,
                    WorkItemModel.work_status == "running",
                )
            )
            or 0
        )
        if running_count > 0:
            return [], True

        finished_count = int(
            self.session.scalar(
                select(func.count())
                .select_from(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job.id,
                    WorkItemModel.work_status.not_in(("queued", "running")),
                )
            )
            or 0
        )
        remaining_required_slots = max(0, _job_required_slots(job) - finished_count)
        if remaining_required_slots == 0:
            return [], True
        if max(0, int(limit or 0)) < remaining_required_slots:
            return [], True

        rows = list(
            self.session.scalars(
                select(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job.id,
                    WorkItemModel.work_status == "queued",
                )
                .order_by(WorkItemModel.priority.desc(), WorkItemModel.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(remaining_required_slots)
            ).all()
        )
        if len(rows) != remaining_required_slots:
            return [], True

        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=max(30, int(lease_seconds or 0)))
        for work in rows:
            work.work_status = "running"
            work.claimed_by = worker_id
            work.claimed_at = now
            work.lease_expires_at = lease_expires_at
            work.started_at = now
            work.updated_at = now
        return rows, True

    def renew_leases(
        self,
        *,
        worker_id: str,
        work_ids: list[str] | None = None,
        claim_generations: dict[str, datetime | None] | None = None,
        lease_seconds: int = DEFAULT_WORK_LEASE_SECONDS,
    ) -> int:
        normalized_claim_generations = dict(claim_generations or {})
        normalized_work_ids = list(
            normalized_claim_generations
            if claim_generations is not None
            else dict.fromkeys(work_ids or [])
        )
        if not normalized_work_ids:
            return 0
        rows = self.session.scalars(
            select(WorkItemModel).where(
                WorkItemModel.id.in_(normalized_work_ids),
                WorkItemModel.work_status == "running",
                WorkItemModel.claimed_by == worker_id,
            )
        ).all()
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=max(30, int(lease_seconds or 0)))
        renewed_count = 0
        for work in rows:
            if (
                claim_generations is not None
                and work.claimed_at != normalized_claim_generations.get(work.id)
            ):
                continue
            work.lease_expires_at = lease_expires_at
            work.updated_at = now
            renewed_count += 1
        return renewed_count

    def release_claimed(
        self,
        *,
        worker_id: str,
        work_ids: list[str] | None = None,
        claim_generations: dict[str, datetime | None] | None = None,
        now: datetime | None = None,
    ) -> int:
        """Return completed-thread claims to the queue without touching other workers."""
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return 0
        normalized_claim_generations = dict(claim_generations or {})
        normalized_work_ids = list(
            normalized_claim_generations
            if claim_generations is not None
            else dict.fromkeys(work_ids or [])
        )
        if (work_ids is not None or claim_generations is not None) and not normalized_work_ids:
            return 0

        stmt = (
            select(WorkItemModel)
            .join(JobModel, JobModel.id == WorkItemModel.job_id)
            .where(
                WorkItemModel.work_status == "running",
                WorkItemModel.claimed_by == normalized_worker_id,
                JobModel.job_status == "running",
            )
            .with_for_update(skip_locked=True)
        )
        if work_ids is not None or claim_generations is not None:
            stmt = stmt.where(WorkItemModel.id.in_(normalized_work_ids))
        rows = self.session.scalars(stmt).all()
        released_at = now or datetime.now(UTC)
        released_count = 0
        for work in rows:
            if (
                claim_generations is not None
                and work.claimed_at != normalized_claim_generations.get(work.id)
            ):
                continue
            work.work_status = "queued"
            work.claimed_by = ""
            work.claimed_at = None
            work.lease_expires_at = None
            work.started_at = None
            work.updated_at = released_at
            released_count += 1
        return released_count

    def expire_claimed(
        self,
        *,
        worker_id: str,
        handoff_delay_s: float = 0,
        now: datetime | None = None,
    ) -> int:
        """Expire this worker's claims after a short process-handoff delay."""
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return 0
        rows = self.session.scalars(
            select(WorkItemModel)
            .join(JobModel, JobModel.id == WorkItemModel.job_id)
            .where(
                WorkItemModel.work_status == "running",
                WorkItemModel.claimed_by == normalized_worker_id,
                JobModel.job_status == "running",
            )
            .with_for_update(skip_locked=True)
        ).all()
        expired_at = now or datetime.now(UTC)
        normalized_handoff_delay_s = max(0.0, float(handoff_delay_s or 0))
        lease_expires_at = (
            expired_at + timedelta(seconds=normalized_handoff_delay_s)
            if normalized_handoff_delay_s
            else expired_at - timedelta(microseconds=1)
        )
        for work in rows:
            work.lease_expires_at = lease_expires_at
            work.updated_at = expired_at
        return len(rows)

    def requeue_expired(self, *, now: datetime | None = None) -> int:
        cutoff = now or datetime.now(UTC)
        rows = self.session.scalars(
            select(WorkItemModel)
            .join(JobModel, JobModel.id == WorkItemModel.job_id)
            .where(
                WorkItemModel.work_status == "running",
                WorkItemModel.lease_expires_at.is_not(None),
                WorkItemModel.lease_expires_at < cutoff,
                JobModel.job_status == "running",
            )
            .with_for_update(skip_locked=True)
        ).all()
        for work in rows:
            work.work_status = "queued"
            work.claimed_by = ""
            work.claimed_at = None
            work.lease_expires_at = None
            work.started_at = None
            work.updated_at = cutoff
        return len(rows)

    def _lock_next_eligible_job(self, *, job_id: str) -> JobModel | None:
        queued = aliased(WorkItemModel)
        running = aliased(WorkItemModel)
        running_with_key = aliased(WorkItemModel)

        running_count = (
            select(func.count())
            .select_from(running)
            .where(
                running.job_id == JobModel.id,
                running.work_status == "running",
            )
            .correlate(JobModel)
            .scalar_subquery()
        )
        work_count_text = JobModel.input_json["work_count"].astext
        work_count = func.greatest(
            cast(func.coalesce(func.nullif(work_count_text, ""), "1"), Integer),
            1,
        )
        same_key_running = exists(
            select(1).where(
                running_with_key.job_id == queued.job_id,
                running_with_key.work_status == "running",
                running_with_key.execution_key == queued.execution_key,
            )
        )
        eligible_work = exists(
            select(1).where(
                queued.job_id == JobModel.id,
                queued.work_status == "queued",
                or_(queued.execution_key == "", ~same_key_running),
            )
        )
        stmt = (
            select(JobModel)
            .where(
                JobModel.job_status == "running",
                func.coalesce(JobModel.input_json["dispatch_mode"].astext, "") != "all_at_once",
                running_count < work_count,
                eligible_work,
            )
            .order_by(JobModel.priority.desc(), JobModel.created_at.asc())
            .with_for_update(skip_locked=True, of=JobModel)
            .limit(1)
        )
        if job_id:
            stmt = stmt.where(JobModel.id == job_id)
        return self.session.scalars(stmt).first()

    def _lock_next_all_at_once_job(self) -> JobModel | None:
        queued = aliased(WorkItemModel)
        eligible_work = exists(
            select(1).where(
                queued.job_id == JobModel.id,
                queued.work_status == "queued",
            )
        )
        return self.session.scalars(
            select(JobModel)
            .where(
                JobModel.job_status == "running",
                JobModel.input_json["dispatch_mode"].astext == "all_at_once",
                eligible_work,
            )
            .order_by(JobModel.priority.desc(), JobModel.created_at.asc())
            .with_for_update(skip_locked=True, of=JobModel)
            .limit(1)
        ).first()

    def _lock_queued_work(self, *, job_id: str, limit: int) -> list[WorkItemModel]:
        rows = list(
            self.session.scalars(
                select(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job_id,
                    WorkItemModel.work_status == "queued",
                    WorkItemModel.execution_key == "",
                )
                .order_by(WorkItemModel.priority.desc(), WorkItemModel.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(limit)
            ).all()
        )
        remaining = limit - len(rows)
        if remaining <= 0:
            return rows

        running_keys = set(
            self.session.scalars(
                select(WorkItemModel.execution_key).where(
                    WorkItemModel.job_id == job_id,
                    WorkItemModel.work_status == "running",
                    WorkItemModel.execution_key != "",
                )
            ).all()
        )
        selected_keys: set[str] = set()
        for _ in range(remaining):
            excluded_keys = running_keys | selected_keys
            stmt = (
                select(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job_id,
                    WorkItemModel.work_status == "queued",
                    WorkItemModel.execution_key != "",
                )
                .order_by(WorkItemModel.priority.desc(), WorkItemModel.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if excluded_keys:
                stmt = stmt.where(WorkItemModel.execution_key.not_in(excluded_keys))
            work = self.session.scalars(stmt).first()
            if work is None:
                break
            rows.append(work)
            selected_keys.add(work.execution_key)
        return rows


def _job_work_count(job: JobModel) -> int:
    try:
        return max(1, int((job.input_json or {}).get("work_count") or 1))
    except (TypeError, ValueError):
        return 1


def _job_required_slots(job: JobModel) -> int:
    try:
        return max(1, int((job.input_json or {}).get("required_slots") or 1))
    except (TypeError, ValueError):
        return 1
