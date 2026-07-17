from __future__ import annotations

from typing import Any, cast

import pytest

from refactor_app.application.workflows.space_seat_expansion import (
    MAX_HTTP_FAILURE_COUNT,
    MAX_NO_PROGRESS_COUNT,
    TARGET_SEATS,
    SpaceSeatExpansionContext,
    SpaceSeatExpansionError,
    SpaceSeatExpansionWorkflow,
    next_seat_count,
)
from refactor_app.plugins.contracts import OpenAIChatGPTProvider


class InMemorySeatProvider:
    def __init__(
        self,
        *,
        seats: int = 2,
        apply_updates: bool = True,
        fail_fetch: bool = False,
        fail_update: bool = False,
    ) -> None:
        self.seats = seats
        self.apply_updates = apply_updates
        self.fail_fetch = fail_fetch
        self.fail_update = fail_update
        self.updated_seats: list[int] = []
        self.fetch_count = 0

    def fetch_subscription(self, **_kwargs: Any) -> dict:
        self.fetch_count += 1
        if self.fail_fetch:
            raise RuntimeError("HTTP 503")
        return {"seats_entitled": self.seats, "seats_in_use": 0}

    def update_subscription_seats(self, *, updated_seats: int, **_kwargs: Any) -> dict:
        self.updated_seats.append(updated_seats)
        if self.fail_update:
            raise RuntimeError("HTTP 429")
        if self.apply_updates:
            self.seats = updated_seats
        return {"ok": True}


class SeatExpansionWorkflowHarness(SpaceSeatExpansionWorkflow):
    def __init__(self, provider: InMemorySeatProvider) -> None:
        super().__init__(
            session_factory=cast(Any, lambda: None),
            openai_provider=cast(OpenAIChatGPTProvider, provider),
            sleep_fn=lambda _seconds: None,
        )
        self.snapshots: list[int] = []

    def _load_context(self, *, space_id: str) -> SpaceSeatExpansionContext:
        return SpaceSeatExpansionContext(
            space_id=space_id,
            external_space_id="workspace-1",
            team_admin_session_id="admin-1",
            access_token="admin-access",
            cookie_header="session=s1",
            proxy_url="http://proxy.example",
        )

    def _write_subscription_snapshot(self, *, space_id: str, subscription: dict) -> None:
        assert space_id == "space-1"
        self.snapshots.append(int(subscription["seats_entitled"]))

    def _write_event(self, **_kwargs: Any) -> None:
        return None


def test_next_seat_count_matches_capped_growth_sequence() -> None:
    values = [2]
    for _ in range(6):
        values.append(next_seat_count(values[-1]))
    assert values == [2, 3, 5, 9, 17, 32, 47]
    assert next_seat_count(998) == TARGET_SEATS


def test_expansion_reaches_fixed_999_target() -> None:
    provider = InMemorySeatProvider()
    result = SeatExpansionWorkflowHarness(provider).run(space_id="space-1")

    assert result["initial_seats"] == 2
    assert result["final_seats"] == TARGET_SEATS
    assert provider.updated_seats[:6] == [3, 5, 9, 17, 32, 47]
    assert provider.updated_seats[-1] == TARGET_SEATS
    assert all(
        1 <= current - previous <= 15
        for previous, current in zip(
            [2, *provider.updated_seats[:-1]], provider.updated_seats, strict=True
        )
    )


def test_expansion_stops_after_ten_no_progress_results() -> None:
    provider = InMemorySeatProvider(apply_updates=False)

    with pytest.raises(SpaceSeatExpansionError, match="made no progress"):
        SeatExpansionWorkflowHarness(provider).run(space_id="space-1")

    assert len(provider.updated_seats) == MAX_NO_PROGRESS_COUNT
    assert provider.fetch_count == MAX_NO_PROGRESS_COUNT + 1


def test_expansion_stops_after_ten_http_failures() -> None:
    provider = InMemorySeatProvider(fail_fetch=True)

    with pytest.raises(SpaceSeatExpansionError, match="HTTP failure limit"):
        SeatExpansionWorkflowHarness(provider).run(space_id="space-1")

    assert provider.fetch_count == MAX_HTTP_FAILURE_COUNT


def test_expansion_stops_after_ten_update_http_failures() -> None:
    provider = InMemorySeatProvider(fail_update=True)

    with pytest.raises(SpaceSeatExpansionError, match="seat update reached HTTP failure limit"):
        SeatExpansionWorkflowHarness(provider).run(space_id="space-1")

    assert len(provider.updated_seats) == MAX_HTTP_FAILURE_COUNT
