from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from refactor_app.api.dependencies import get_db_session
from refactor_app.api.pagination import page_payload, page_values, total_for
from refactor_app.application.jobs.queue import JobQueue
from refactor_app.infrastructure.db.models import (
    JobEventModel,
    JobModel,
    JobRunModel,
    JobStepModel,
    UserAccountModel,
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
def list_jobs(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    status: str = "",
    type: str = "",
    created_by: str = "",
    error_code: str = "",
    q: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = select(JobModel)
    if status.strip():
        stmt = stmt.where(JobModel.job_status.in_(_csv_values(status)))
    if type.strip():
        stmt = stmt.where(JobModel.type.in_(_csv_values(type)))
    if created_by.strip():
        stmt = stmt.where(JobModel.created_by.ilike(f"%{created_by.strip()}%"))
    if error_code.strip():
        stmt = stmt.where(
            JobModel.id.in_(
                select(JobRunModel.job_id).where(
                    JobRunModel.error_code.ilike(f"{error_code.strip()}%")
                )
            )
        )
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                JobModel.id.ilike(needle),
                JobModel.type.ilike(needle),
                JobModel.created_by.ilike(needle),
            )
        )
    sort_columns = {
        "created_at": JobModel.created_at,
        "updated_at": JobModel.updated_at,
        "priority": JobModel.priority,
        "status": JobModel.job_status,
        "type": JobModel.type,
    }
    stmt, normalized_sort = _apply_sort(stmt, sort, sort_columns, default="-created_at")
    total = total_for(session, stmt)
    jobs = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    progress = _job_progress(session, [job.id for job in jobs])
    return page_payload(
        items=[
            {**_job_dict(job), "progress": progress.get(job.id, _empty_progress())}
            for job in jobs
        ],
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


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
    if job.job_status in {"succeeded", "failed"}:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "completed jobs cannot be cancelled",
                "job_status": job.job_status,
            },
        )

    now = datetime.now(UTC)
    job.job_status = "cancelled"
    job.updated_at = now
    queued_work_items = session.scalars(
        select(WorkItemModel).where(
            WorkItemModel.job_id == job_id,
            WorkItemModel.work_status == "queued",
        )
    ).all()
    for work in queued_work_items:
        work.work_status = "cancelled"
        work.finished_at = now
        work.lease_expires_at = None
        work.error_code = "cancelled_by_operator"
        work.error_message = "job cancelled by operator"
        work.updated_at = now
    running_runs = session.scalars(
        select(JobRunModel).where(
            JobRunModel.job_id == job_id,
            JobRunModel.run_status == "running",
        )
    ).all()
    for run in running_runs:
        run.run_status = "cancelled"
        run.finished_at = now
        run.error_code = "cancelled_by_operator"
        run.error_message = "job cancelled by operator"

    deleted_placeholder_count = 0
    if job.type == "account.protocol_register":
        active_work_items = session.scalars(
            select(WorkItemModel).where(
                WorkItemModel.job_id == job_id,
                WorkItemModel.work_status.in_(("queued", "running", "cancelled")),
            )
        ).all()
        placeholder_ids = {
            str((work.output_json or {}).get("user_account_id") or "").strip()
            for work in active_work_items
        }
        placeholder_ids.discard("")
        if placeholder_ids:
            placeholders = session.scalars(
                select(UserAccountModel).where(
                    UserAccountModel.id.in_(placeholder_ids),
                    UserAccountModel.account_status == "registering",
                )
            ).all()
            for account in placeholders:
                session.delete(account)
            deleted_placeholder_count = len(placeholders)
    elif job.type == "account.change_email.bulk":
        placeholder_ids = {
            str((work.input_json or {}).get("user_account_id") or "").strip()
            for work in queued_work_items
        }
        placeholder_ids.discard("")
        if placeholder_ids:
            placeholders = session.scalars(
                select(UserAccountModel).where(
                    UserAccountModel.id.in_(placeholder_ids),
                    UserAccountModel.account_status == "registering",
                )
            ).all()
            for account in placeholders:
                session.delete(account)
            deleted_placeholder_count = len(placeholders)
    session.commit()
    return {
        **_job_dict(job),
        "cancelled_work_count": len(queued_work_items),
        "deleted_placeholder_count": deleted_placeholder_count,
        "running_work_count": session.scalar(
            select(func.count())
            .select_from(WorkItemModel)
            .where(
                WorkItemModel.job_id == job_id,
                WorkItemModel.work_status == "running",
            )
        )
        or 0,
    }


@router.get("/jobs/{job_id}/work-items")
def get_job_work_items(
    job_id: str,
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "created_at",
    status: str = "",
    q: str = "",
) -> dict:
    if session.get(JobModel, job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    page, page_size = page_values(page, page_size)
    stmt = select(WorkItemModel).where(WorkItemModel.job_id == job_id)
    if status.strip():
        stmt = stmt.where(WorkItemModel.work_status.in_(_csv_values(status)))
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                WorkItemModel.id.ilike(needle),
                WorkItemModel.work_type.ilike(needle),
                WorkItemModel.error_code.ilike(needle),
                WorkItemModel.error_message.ilike(needle),
            )
        )
    sort_columns = {
        "created_at": WorkItemModel.created_at,
        "started_at": WorkItemModel.started_at,
        "finished_at": WorkItemModel.finished_at,
        "status": WorkItemModel.work_status,
    }
    stmt, normalized_sort = _apply_sort(stmt, sort, sort_columns, default="created_at")
    total = total_for(session, stmt)
    rows = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return page_payload(
        items=[_work_item_dict(work) for work in rows],
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


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
def get_run_events(
    run_id: str,
    session: DbSession,
    page: int = 1,
    page_size: int = 100,
    sort: str = "ts",
    level: str = "",
    event_type: str = "",
    work_id: str = "",
    q: str = "",
    after_ts: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = select(JobEventModel).where(JobEventModel.run_id == run_id)
    if level.strip():
        stmt = stmt.where(JobEventModel.level.in_([item.upper() for item in _csv_values(level)]))
    if event_type.strip():
        stmt = stmt.where(JobEventModel.event_type.ilike(f"%{event_type.strip()}%"))
    if work_id.strip():
        stmt = stmt.where(JobEventModel.data_json["work_id"].as_string() == work_id.strip())
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                JobEventModel.event_type.ilike(needle),
                JobEventModel.message.ilike(needle),
            )
        )
    if after_ts.strip():
        try:
            parsed = datetime.fromisoformat(after_ts.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid after_ts") from exc
        stmt = stmt.where(JobEventModel.ts > parsed)
    stmt, normalized_sort = _apply_sort(
        stmt,
        sort,
        {
            "ts": JobEventModel.ts,
            "level": JobEventModel.level,
            "event_type": JobEventModel.event_type,
        },
        default="ts",
    )
    total = total_for(session, stmt)
    events = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    items = [
        {
            "id": event.id,
            "run_id": event.run_id,
            "step_id": event.step_id,
            "ts": event.ts.isoformat(),
            "level": event.level,
            "event_type": event.event_type,
            "message": event.message,
            "data_json": _redact_value(event.data_json),
        }
        for event in events
    ]
    return page_payload(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


@router.get("/jobs/{job_id}/summary")
def get_job_summary(job_id: str, session: DbSession) -> dict:
    job = session.get(JobModel, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    progress = _job_progress(session, [job_id]).get(job_id, _empty_progress())
    latest_run = session.scalar(
        select(JobRunModel)
        .where(JobRunModel.job_id == job_id)
        .order_by(JobRunModel.attempt.desc())
        .limit(1)
    )
    latest_event = None
    if latest_run is not None:
        latest_event = session.scalar(
            select(JobEventModel)
            .where(JobEventModel.run_id == latest_run.id)
            .order_by(JobEventModel.ts.desc())
            .limit(1)
        )
    return {
        **_job_dict(job),
        "progress": progress,
        "run": _run_dict(latest_run) if latest_run is not None else None,
        "latest_event": {
            "ts": latest_event.ts.isoformat(),
            "level": latest_event.level,
            "event_type": latest_event.event_type,
            "message": latest_event.message,
            "data_json": _redact_value(latest_event.data_json),
        }
        if latest_event is not None
        else None,
    }


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
        "input_json": _redact_value(job.input_json),
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
        "output_json": _redact_value(run.output_json),
    }


def _work_item_dict(work: WorkItemModel) -> dict:
    return {
        "id": work.id,
        "job_id": work.job_id,
        "work_type": work.work_type,
        "work_status": work.work_status,
        "priority": work.priority,
        "execution_key": work.execution_key,
        "input_json": _redact_value(work.input_json),
        "output_json": _redact_value(work.output_json),
        "error_code": work.error_code,
        "error_message": work.error_message,
        "claimed_by": work.claimed_by,
        "claimed_at": work.claimed_at.isoformat() if work.claimed_at else "",
        "lease_expires_at": work.lease_expires_at.isoformat() if work.lease_expires_at else "",
        "started_at": work.started_at.isoformat() if work.started_at else "",
        "finished_at": work.finished_at.isoformat() if work.finished_at else "",
        "created_at": work.created_at.isoformat(),
        "updated_at": work.updated_at.isoformat(),
    }


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _apply_sort(stmt, sort: str, columns: dict[str, Any], *, default: str):
    requested = (sort or default).strip()
    descending = requested.startswith("-")
    key = requested[1:] if descending else requested
    if key not in columns:
        requested = default
        descending = requested.startswith("-")
        key = requested[1:] if descending else requested
    column = columns[key]
    return stmt.order_by(column.desc() if descending else column.asc()), requested


def _empty_progress() -> dict[str, int]:
    return {
        "total": 0,
        "queued": 0,
        "running": 0,
        "succeeded": 0,
        "skipped": 0,
        "failed": 0,
        "cancelled": 0,
    }


def _job_progress(session: Session, job_ids: list[str]) -> dict[str, dict[str, int]]:
    result = {job_id: _empty_progress() for job_id in job_ids}
    if not job_ids:
        return result
    rows = session.execute(
        select(WorkItemModel.job_id, WorkItemModel.work_status, func.count())
        .where(WorkItemModel.job_id.in_(job_ids))
        .group_by(WorkItemModel.job_id, WorkItemModel.work_status)
    ).all()
    for job_id, status, count in rows:
        progress = result.setdefault(str(job_id), _empty_progress())
        if str(status) in progress:
            progress[str(status)] = int(count or 0)
        progress["total"] += int(count or 0)
    return result


_SENSITIVE_KEY_RE = re.compile(
    r"(^|_)(access_token|refresh_token|session_token|cookie|cookie_header|auth_cookie_header|"
    r"authorization|admin_key|custom_auth_header_value|password|csrf_token|code_verifier|otp_code|"
    r"claim_token|api_key|pt)($|_)",
    re.IGNORECASE,
)
_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)(access_token|refresh_token|session_token|authorization|cookie|password|csrf_token|"
    r"code_verifier|otp_code)=([^&\s]+)"
)


def _redact_value(value: Any, *, key: str = "") -> Any:
    if key.endswith("_cookie_names") and isinstance(value, list):
        return [str(item) for item in value]
    if _SENSITIVE_KEY_RE.search(key):
        return "<redacted>" if value not in (None, "") else value
    if isinstance(value, dict):
        return {
            str(item_key): _redact_value(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        if key in {"request_url", "response_url", "location"} or key.endswith("_url"):
            return _redact_url(value)
        return _SENSITIVE_TEXT_RE.sub(lambda match: f"{match.group(1)}=<redacted>", value)
    return value


def _redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        query = []
        for name, item in parse_qsl(parsed.query, keep_blank_values=True):
            if _SENSITIVE_KEY_RE.search(name) or name.lower() in {"code", "state"}:
                query.append((name, "<redacted>"))
            else:
                query.append((name, item))
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
        )
    except ValueError:
        return value
