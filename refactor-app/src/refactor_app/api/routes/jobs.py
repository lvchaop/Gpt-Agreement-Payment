from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.api.dependencies import get_db_session
from refactor_app.application.jobs.queue import JobQueue
from refactor_app.infrastructure.db.models import (
    JobEventModel,
    JobModel,
    JobRunModel,
    JobStepModel,
    WorkItemModel,
)

router = APIRouter(tags=["jobs"])
DbSession = Annotated[Session, Depends(get_db_session)]


class CreateJobRequest(BaseModel):
    type: str
    input_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str = ""
    priority: int = 0


@router.post("/jobs")
def create_job(req: CreateJobRequest, session: DbSession) -> dict:
    job = JobQueue(session).enqueue(
        job_type=req.type,
        input_json=req.input_json,
        created_by=req.created_by,
        priority=req.priority,
    )
    session.commit()
    return {"job_id": job.id, "job_status": job.job_status}


@router.get("/jobs")
def list_jobs(session: DbSession, limit: int = 100) -> list[dict]:
    jobs = session.scalars(select(JobModel).order_by(JobModel.created_at.desc()).limit(limit)).all()
    return [_job_dict(job) for job in jobs]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, session: DbSession) -> dict:
    job = session.get(JobModel, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_dict(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, session: DbSession) -> dict:
    job = session.get(JobModel, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.job_status == "queued":
        job.job_status = "cancelled"
        job.updated_at = datetime.now(UTC)
    elif job.job_status not in {"cancelled", "succeeded"}:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "only queued trigger jobs can be cancelled directly",
                "job_status": job.job_status,
            },
        )

    now = datetime.now(UTC)
    queued_work_items = session.scalars(
        select(WorkItemModel).where(
            WorkItemModel.job_id == job_id,
            WorkItemModel.work_status == "queued",
        )
    ).all()
    for work in queued_work_items:
        work.work_status = "cancelled"
        work.finished_at = now
        work.updated_at = now
    session.commit()
    return {**_job_dict(job), "cancelled_work_count": len(queued_work_items)}


@router.get("/jobs/{job_id}/work-items")
def get_job_work_items(job_id: str, session: DbSession) -> list[dict]:
    if session.get(JobModel, job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    work_items = session.scalars(
        select(WorkItemModel)
        .where(WorkItemModel.job_id == job_id)
        .order_by(WorkItemModel.created_at)
    ).all()
    return [_work_item_dict(work) for work in work_items]


@router.post("/work-items/{work_item_id}/cancel")
def cancel_work_item(work_item_id: str, session: DbSession) -> dict:
    work = session.get(WorkItemModel, work_item_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work item not found")
    if work.work_status == "cancelled":
        return _work_item_dict(work)
    if work.work_status != "queued":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "only queued work items can be cancelled",
                "work_status": work.work_status,
            },
        )
    now = datetime.now(UTC)
    work.work_status = "cancelled"
    work.finished_at = now
    work.updated_at = now
    session.commit()
    return _work_item_dict(work)


@router.get("/jobs/{job_id}/runs")
def get_job_runs(job_id: str, session: DbSession) -> list[dict]:
    runs = session.scalars(
        select(JobRunModel).where(JobRunModel.job_id == job_id).order_by(JobRunModel.started_at)
    ).all()
    return [_run_dict(run) for run in runs]


@router.get("/runs/{run_id}/events")
def get_run_events(run_id: str, session: DbSession) -> list[dict]:
    events = session.scalars(
        select(JobEventModel).where(JobEventModel.run_id == run_id).order_by(JobEventModel.ts)
    ).all()
    return [
        {
            "id": event.id,
            "run_id": event.run_id,
            "step_id": event.step_id,
            "ts": event.ts.isoformat(),
            "level": event.level,
            "event_type": event.event_type,
            "message": event.message,
            "data_json": event.data_json,
        }
        for event in events
    ]


@router.get("/runs/{run_id}/steps")
def get_run_steps(run_id: str, session: DbSession) -> list[dict]:
    steps = session.scalars(
        select(JobStepModel).where(JobStepModel.run_id == run_id).order_by(JobStepModel.started_at)
    ).all()
    return [
        {
            "id": step.id,
            "run_id": step.run_id,
            "name": step.name,
            "step_status": step.step_status,
            "attempt": step.attempt,
            "started_at": step.started_at.isoformat() if step.started_at else "",
            "finished_at": step.finished_at.isoformat() if step.finished_at else "",
            "input_json": step.input_json,
            "output_json": step.output_json,
            "error_code": step.error_code,
            "error_message": step.error_message,
        }
        for step in steps
    ]


def _job_dict(job: JobModel) -> dict:
    return {
        "id": job.id,
        "type": job.type,
        "job_status": job.job_status,
        "priority": job.priority,
        "input_json": job.input_json,
        "created_by": job.created_by,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _run_dict(run: JobRunModel) -> dict:
    return {
        "id": run.id,
        "job_id": run.job_id,
        "run_status": run.run_status,
        "attempt": run.attempt,
        "started_at": run.started_at.isoformat() if run.started_at else "",
        "finished_at": run.finished_at.isoformat() if run.finished_at else "",
        "error_code": run.error_code,
        "error_message": run.error_message,
        "output_json": run.output_json,
    }


def _work_item_dict(work: WorkItemModel) -> dict:
    return {
        "id": work.id,
        "job_id": work.job_id,
        "work_type": work.work_type,
        "work_status": work.work_status,
        "priority": work.priority,
        "input_json": work.input_json,
        "output_json": work.output_json,
        "error_code": work.error_code,
        "error_message": work.error_message,
        "claimed_by": work.claimed_by,
        "claimed_at": work.claimed_at.isoformat() if work.claimed_at else "",
        "started_at": work.started_at.isoformat() if work.started_at else "",
        "finished_at": work.finished_at.isoformat() if work.finished_at else "",
        "created_at": work.created_at.isoformat(),
        "updated_at": work.updated_at.isoformat(),
    }
