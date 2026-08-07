from __future__ import annotations

from refactor_app.infrastructure.logging.event_writer import EventWriter


def test_empty_step_id_is_written_as_null() -> None:
    added = []

    class Session:
        def add(self, value) -> None:
            added.append(value)

    event = EventWriter(Session()).write(
        run_id="run-1",
        event_type="test.event",
        message="test",
        step_id="",
    )

    assert event.step_id is None
    assert added == [event]
