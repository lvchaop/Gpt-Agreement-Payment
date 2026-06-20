from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.models import JobEventModel


class EventWriter:
    def __init__(self, session: Session) -> None:
        self.session = session

    def write(
        self,
        *,
        run_id: str,
        event_type: str,
        message: str,
        level: str = "INFO",
        step_id: str | None = None,
        data_json: dict | None = None,
    ) -> JobEventModel:
        event = JobEventModel(
            id=str(uuid4()),
            run_id=run_id,
            step_id=step_id,
            ts=datetime.now(UTC),
            level=level,
            event_type=event_type,
            message=message,
            data_json=data_json or {},
        )
        self.session.add(event)
        return event
