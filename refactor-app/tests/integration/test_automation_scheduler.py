from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from refactor_app.api.routes import resources
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine
from refactor_app.infrastructure.db.models import AutomationScheduleModel


def _schedule(
    *,
    schedule_id: str,
    schedule_type: str,
    config_json: dict[str, Any],
    next_run_at: datetime,
) -> AutomationScheduleModel:
    now = datetime.now(UTC)
    return AutomationScheduleModel(
        id=schedule_id,
        schedule_type=schedule_type,
        schedule_status="active",
        enabled=True,
        interval_seconds=60,
        config_json=config_json,
        last_run_at=None,
        next_run_at=next_run_at,
        last_job_id="",
        last_run_status="",
        locked_by="",
        locked_until=None,
        last_error_code="",
        last_error_message="",
        created_by="test",
        created_at=now,
        updated_at=now,
    )


def test_failed_schedule_does_not_block_later_due_schedule(monkeypatch) -> None:
    engine = make_engine(Settings())
    calls: list[str] = []
    before = datetime.now(UTC)

    def fake_execute(*, session, schedule, **_kwargs):
        del session
        calls.append(schedule.schedule_type)
        if schedule.schedule_type == "automation.space_authorize":
            raise RuntimeError("synthetic authorize failure")
        schedule.last_run_at = datetime.now(UTC)
        schedule.next_run_at = datetime.now(UTC) + timedelta(seconds=60)
        schedule.last_run_status = "succeeded"
        return {"items": []}

    monkeypatch.setattr(resources, "_execute_space_automation_schedule", fake_execute)

    with engine.connect() as connection:
        connection.execute(
            text(
                "CREATE TEMP TABLE automation_schedules "
                "(LIKE public.automation_schedules INCLUDING ALL) "
                "ON COMMIT PRESERVE ROWS"
            )
        )
        connection.commit()
        with Session(bind=connection, autoflush=False, expire_on_commit=False) as session:
            session.add_all(
                [
                    _schedule(
                        schedule_id="test-schedule-authorize",
                        schedule_type="automation.space_authorize",
                        config_json={"work_count": 1},
                        next_run_at=before - timedelta(minutes=2),
                    ),
                    _schedule(
                        schedule_id="test-schedule-downstream",
                        schedule_type="automation.space_downstream_push",
                        config_json={"work_count": 5},
                        next_run_at=before - timedelta(minutes=1),
                    ),
                ]
            )
            session.commit()

            resources._run_due_space_automation_schedules(
                session=session,
                scheduler_id="test-scheduler",
            )

            rows = {
                row.schedule_type: row
                for row in session.scalars(select(AutomationScheduleModel)).all()
            }

    engine.dispose()

    assert calls == [
        "automation.space_authorize",
        "automation.space_downstream_push",
    ]
    failed = rows["automation.space_authorize"]
    assert failed.last_run_status == "failed"
    assert failed.last_error_code == "schedule_run_failed"
    assert failed.last_error_message == "RuntimeError: synthetic authorize failure"
    assert failed.next_run_at is not None and failed.next_run_at > before
    assert failed.locked_by == ""
    assert failed.locked_until is None

    downstream = rows["automation.space_downstream_push"]
    assert downstream.last_run_status == "succeeded"
    assert downstream.next_run_at is not None and downstream.next_run_at > before
    assert downstream.locked_by == ""
    assert downstream.locked_until is None
