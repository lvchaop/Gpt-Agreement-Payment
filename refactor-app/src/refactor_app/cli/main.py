from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
batch_app = typer.Typer(no_args_is_help=True)
codex_app = typer.Typer(no_args_is_help=True)
mail_app = typer.Typer(no_args_is_help=True)
membership_app = typer.Typer(no_args_is_help=True)

app.add_typer(db_app, name="db")
app.add_typer(worker_app, name="worker")
app.add_typer(job_app, name="job")
app.add_typer(webshare_app, name="webshare")
app.add_typer(batch_app, name="batch")
app.add_typer(codex_app, name="codex")
app.add_typer(mail_app, name="mail")
app.add_typer(membership_app, name="membership")


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
    with engine.connect() as connection:
        has_base_schema = connection.execute(
            text("SELECT to_regclass('public.user_accounts') IS NOT NULL")
        ).scalar_one()
    for sql_path in sql_paths:
        if has_base_schema and sql_path.name == "001_initial_schema.sql":
            typer.echo(f"skip {sql_path.name}")
            continue
        connection = engine.raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql_path.read_text())
            connection.commit()
        finally:
            connection.close()
        typer.echo(f"applied {sql_path.name}")
    typer.echo("ok")


@worker_app.command("run")
def worker_run(once: bool = True, concurrency: int = 1) -> None:
    settings = Settings()
    session_factory = _session_factory(settings)
    if concurrency < 1:
        raise typer.BadParameter("concurrency must be >= 1")
    if concurrency > settings.worker_max_concurrency:
        raise typer.BadParameter(
            f"concurrency must be <= {settings.worker_max_concurrency}"
        )
    if concurrency > 1:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(_run_worker_loop, session_factory, settings, once)
                for _ in range(concurrency)
            ]
            for future in as_completed(futures):
                for result in future.result():
                    typer.echo(result)
        return

    for result in _run_worker_loop(session_factory, settings, once):
        typer.echo(result)


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


@batch_app.command("create")
def batch_create(team_workspace_id: str, user_account_ids_csv: str, codex_client_id: str) -> None:
    _enqueue_and_echo(
        "workspace_join_batch.run",
        {
            "team_workspace_id": team_workspace_id,
            "user_account_ids": [
                value.strip() for value in user_account_ids_csv.split(",") if value.strip()
            ],
            "codex_client_id": codex_client_id,
        },
    )


@batch_app.command("activate")
def batch_activate(batch_id: str) -> None:
    _enqueue_and_echo("workspace_join_batch.activate", {"batch_id": batch_id})


@membership_app.command("probe")
def membership_probe(membership_id: str) -> None:
    _enqueue_and_echo("membership.probe", {"membership_id": membership_id})


@membership_app.command("invite-member")
def membership_invite_member(inviter_membership_id: str, email: str) -> None:
    _enqueue_and_echo(
        "membership.invite_member",
        {"inviter_membership_id": inviter_membership_id, "email": email},
    )


@codex_app.command("heartbeat")
def codex_heartbeat(credential_id: str) -> None:
    _enqueue_and_echo("codex_credential.heartbeat", {"codex_credential_id": credential_id})


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
