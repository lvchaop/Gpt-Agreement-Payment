from __future__ import annotations

import json
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import typer
from sqlalchemy import text

from refactor_app.application.jobs.handlers import register_core_handlers
from refactor_app.application.jobs.queue import JobQueue
from refactor_app.application.jobs.runner import JobRunner
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory

app = typer.Typer(no_args_is_help=True)
db_app = typer.Typer(no_args_is_help=True)
worker_app = typer.Typer(no_args_is_help=True)
job_app = typer.Typer(no_args_is_help=True)
webshare_app = typer.Typer(no_args_is_help=True)
mail_app = typer.Typer(no_args_is_help=True)

app.add_typer(db_app, name="db")
app.add_typer(worker_app, name="worker")
app.add_typer(job_app, name="job")
app.add_typer(webshare_app, name="webshare")
app.add_typer(mail_app, name="mail")


@db_app.command("check")
def health() -> None:
    settings = Settings()
    engine = make_engine(settings)
    with engine.connect():
        typer.echo("ok")


@db_app.command("migrate")
def migrate() -> None:
    sql_dir = Path(__file__).resolve().parents[3] / "migrations" / "sql"
    sql_paths = sorted(sql_dir.glob("*.sql"))
    engine = make_engine(Settings())
    with engine.begin() as connection:
        has_base_schema = connection.execute(
            text("SELECT to_regclass('public.user_accounts') IS NOT NULL")
        ).scalar_one()
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  filename TEXT PRIMARY KEY,
                  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        applied = {
            row[0]
            for row in connection.execute(text("SELECT filename FROM schema_migrations")).all()
        }
        if has_base_schema and not applied:
            legacy_names = [
                path.name
                for path in sql_paths
                if path.name < "029_user_account_access_token_and_space_jobs.sql"
            ]
            for filename in legacy_names:
                connection.execute(
                    text(
                        """
                        INSERT INTO schema_migrations(filename)
                        VALUES (:filename)
                        ON CONFLICT (filename) DO NOTHING
                        """
                    ),
                    {"filename": filename},
                )
            applied.update(legacy_names)
    for sql_path in sql_paths:
        if sql_path.name in applied:
            typer.echo(f"skip {sql_path.name}")
            continue
        connection = engine.raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql_path.read_text())
                cursor.execute(
                    """
                    INSERT INTO schema_migrations(filename)
                    VALUES (%s)
                    ON CONFLICT (filename) DO NOTHING
                    """,
                    (sql_path.name,),
                )
            connection.commit()
        finally:
            connection.close()
        typer.echo(f"applied {sql_path.name}")
    typer.echo("ok")


@worker_app.command("run")
def worker_run(
    once: bool = True,
    capacity: int = typer.Option(0, "--capacity"),
) -> None:
    settings = Settings()
    session_factory = _session_factory(settings)
    worker_capacity = int(capacity or settings.worker_capacity)
    if worker_capacity < 1:
        raise typer.BadParameter("capacity must be >= 1")
    if worker_capacity > settings.worker_capacity:
        raise typer.BadParameter(f"capacity must be <= {settings.worker_capacity}")
    if once:
        for result in _run_worker_loop(session_factory, settings, True):
            typer.echo(result)
        return
    _run_worker_dispatch_loop(
        session_factory=session_factory,
        settings=settings,
        capacity=worker_capacity,
    )


def _run_worker_dispatch_loop(*, session_factory, settings: Settings, capacity: int) -> None:
    runner = JobRunner(session_factory)
    register_core_handlers(runner, session_factory=session_factory, settings=settings)
    runner.requeue_expired_work()
    futures: dict[Future, tuple[str, str]] = {}
    last_lease_renewal = time.monotonic()
    last_expired_requeue = time.monotonic()

    with ThreadPoolExecutor(max_workers=capacity) as executor:
        while True:
            for future in [item for item in futures if item.done()]:
                task_type, task_id = futures.pop(future)
                try:
                    future.result()
                except Exception as exc:
                    typer.echo(f"worker {task_type} {task_id} crashed: {type(exc).__name__}: {exc}")

            now = time.monotonic()
            if now - last_lease_renewal >= 30:
                active_work_ids = [
                    task_id for task_type, task_id in futures.values() if task_type == "work"
                ]
                runner.renew_work_leases(active_work_ids)
                last_lease_renewal = now
            if now - last_expired_requeue >= 60:
                runner.requeue_expired_work()
                last_expired_requeue = now

            free_slots = capacity - len(futures)
            made_progress = False
            blocks_normal_dispatch = False
            if free_slots > 0:
                work_ids, blocks_normal_dispatch = runner.claim_all_at_once_work_batch(
                    max_count=free_slots
                )
                for work_id in work_ids:
                    future = executor.submit(runner.run_claimed_work, work_id)
                    futures[future] = ("work", work_id)
                free_slots -= len(work_ids)
                if work_ids:
                    made_progress = True

            if free_slots > 0 and not blocks_normal_dispatch:
                claimed_job = runner.claim_next_job()
                if claimed_job is not None:
                    job_id, run_id = claimed_job
                    future = executor.submit(
                        runner.run_claimed_job,
                        job_id=job_id,
                        run_id=run_id,
                    )
                    futures[future] = ("job", job_id)
                    free_slots -= 1
                    made_progress = True

            while free_slots > 0 and not blocks_normal_dispatch:
                work_ids = runner.claim_work_batch(max_count=free_slots)
                if not work_ids:
                    break
                for work_id in work_ids:
                    future = executor.submit(runner.run_claimed_work, work_id)
                    futures[future] = ("work", work_id)
                free_slots -= len(work_ids)
                made_progress = True

            time.sleep(0.05 if made_progress else 0.5)


def _run_worker_loop(session_factory, settings: Settings, once: bool) -> list[str]:
    results: list[str] = []
    runner = JobRunner(session_factory)
    register_core_handlers(runner, session_factory=session_factory, settings=settings)
    while True:
        job_id = runner.run_one()
        if job_id is None:
            if once:
                results.append("no_job")
                return results
            time.sleep(1)
            continue
        if not once:
            continue
        results.append(job_id)
        return results


@job_app.command("enqueue")
def job_enqueue(job_type: str, input_json: str = "{}", created_by: str = "cli") -> None:
    payload = json.loads(input_json)
    session_factory = _session_factory()
    with session_factory() as session:
        job = JobQueue(session).enqueue(
            job_type=job_type,
            input_json=payload,
            created_by=created_by,
        )
        session.commit()
        typer.echo(job.id)


@webshare_app.command("refresh")
def webshare_refresh() -> None:
    _enqueue_and_echo("proxy.refresh_webshare_pool", {})


@mail_app.command("allocate")
def mail_allocate(user_account_id: str = "", purpose: str = "") -> None:
    _enqueue_and_echo(
        "mail.allocate",
        {"user_account_id": user_account_id or None, "purpose": purpose},
    )


@mail_app.command("poll-otp")
def mail_poll_otp(mail_lease_id: str, timeout_s: int = 60) -> None:
    _enqueue_and_echo("mail.poll_otp", {"mail_lease_id": mail_lease_id, "timeout_s": timeout_s})


@mail_app.command("mark-used")
def mail_mark_used(mail_lease_id: str) -> None:
    _enqueue_and_echo("mail.mark_used", {"mail_lease_id": mail_lease_id})


@mail_app.command("mark-failed")
def mail_mark_failed(
    mail_lease_id: str,
    failure_code: str = "",
    failure_message: str = "",
) -> None:
    _enqueue_and_echo(
        "mail.mark_failed",
        {
            "mail_lease_id": mail_lease_id,
            "failure_code": failure_code,
            "failure_message": failure_message,
        },
    )


@mail_app.command("release")
def mail_release(mail_lease_id: str, reason: str = "") -> None:
    _enqueue_and_echo("mail.release", {"mail_lease_id": mail_lease_id, "reason": reason})


def _session_factory(settings: Settings | None = None):
    return make_session_factory(make_engine(settings or Settings()))


def _enqueue_and_echo(job_type: str, input_json: dict) -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        job = JobQueue(session).enqueue(job_type=job_type, input_json=input_json, created_by="cli")
        session.commit()
        typer.echo(job.id)


if __name__ == "__main__":
    app()
