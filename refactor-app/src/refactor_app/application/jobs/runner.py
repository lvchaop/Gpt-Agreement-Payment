from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from socket import gethostname
from uuid import uuid4

from sqlalchemy.orm import Session

from refactor_app.application.jobs.queue import JobQueue, WorkQueue
from refactor_app.infrastructure.db.models import (
    CodexOAuthCredentialModel,
    JobRunModel,
    MembershipModel,
    TeamWorkspaceModel,
    UserAccountModel,
    WorkItemModel,
    WorkspaceJoinBatchItemModel,
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
        work.output_json = output_json
    work.updated_at = now


def _work_context(session: Session, input_json: dict) -> dict:
    user_account_id = str(input_json.get("user_account_id") or "")
    team_workspace_id = str(input_json.get("team_workspace_id") or "")
    membership_id = str(input_json.get("membership_id") or "")
    codex_credential_id = str(input_json.get("codex_credential_id") or "")
    batch_item_id = str(input_json.get("batch_item_id") or "")

    if membership_id:
        membership = session.get(MembershipModel, membership_id)
        if membership is not None:
            user_account_id = user_account_id or membership.user_account_id
            team_workspace_id = team_workspace_id or membership.team_workspace_id

    if codex_credential_id:
        credential = session.get(CodexOAuthCredentialModel, codex_credential_id)
        if credential is not None:
            user_account_id = user_account_id or credential.user_account_id
            team_workspace_id = team_workspace_id or credential.team_workspace_id

    if batch_item_id:
        batch_item = session.get(WorkspaceJoinBatchItemModel, batch_item_id)
        if batch_item is not None:
            user_account_id = user_account_id or batch_item.user_account_id
            team_workspace_id = team_workspace_id or batch_item.team_workspace_id
            membership_id = membership_id or str(batch_item.membership_id or "")
            codex_credential_id = codex_credential_id or str(batch_item.codex_credential_id or "")

    account = session.get(UserAccountModel, user_account_id) if user_account_id else None
    workspace = session.get(TeamWorkspaceModel, team_workspace_id) if team_workspace_id else None
    return {
        "user_account_id": user_account_id,
        "email": account.email if account is not None else "",
        "team_workspace_id": team_workspace_id,
        "external_workspace_id": workspace.external_workspace_id if workspace is not None else "",
        "workspace_name": workspace.name if workspace is not None else "",
        "membership_id": membership_id,
        "codex_credential_id": codex_credential_id,
        "batch_item_id": batch_item_id,
    }
