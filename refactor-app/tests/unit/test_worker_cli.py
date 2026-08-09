from __future__ import annotations

from concurrent.futures import Future
from datetime import UTC, datetime

from refactor_app.cli.main import _collect_completed_worker_futures


class _RecordingRunner:
    def __init__(self) -> None:
        self.released: list[dict[str, datetime | None] | None] = []

    def release_claimed_work(
        self,
        work_ids: list[str] | None = None,
        *,
        claim_generations: dict[str, datetime | None] | None = None,
    ) -> int:
        self.released.append(claim_generations)
        return len(claim_generations or work_ids or [])


def test_completed_crashed_work_is_released_immediately() -> None:
    runner = _RecordingRunner()
    claimed_at = datetime(2026, 8, 9, tzinfo=UTC)
    future: Future[None] = Future()
    future.set_exception(RuntimeError("database connection lost"))
    futures = {future: ("work", "work-1", claimed_at)}

    _collect_completed_worker_futures(futures=futures, runner=runner)  # type: ignore[arg-type]

    assert futures == {}
    assert runner.released == [{"work-1": claimed_at}]


def test_completed_job_or_successful_work_does_not_release_claim() -> None:
    runner = _RecordingRunner()
    successful_work: Future[None] = Future()
    successful_work.set_result(None)
    crashed_job: Future[None] = Future()
    crashed_job.set_exception(RuntimeError("job crashed"))
    futures = {
        successful_work: ("work", "work-success", datetime(2026, 8, 9, tzinfo=UTC)),
        crashed_job: ("job", "job-1", None),
    }

    _collect_completed_worker_futures(futures=futures, runner=runner)  # type: ignore[arg-type]

    assert futures == {}
    assert runner.released == []


def test_failed_claim_release_keeps_completed_future_for_retry() -> None:
    class _FailingRunner(_RecordingRunner):
        def release_claimed_work(
            self,
            work_ids: list[str] | None = None,
            *,
            claim_generations: dict[str, datetime | None] | None = None,
        ) -> int:
            raise RuntimeError("database unavailable")

    runner = _FailingRunner()
    claimed_at = datetime(2026, 8, 9, tzinfo=UTC)
    future: Future[None] = Future()
    future.set_exception(RuntimeError("worker crashed"))
    futures = {future: ("work", "work-1", claimed_at)}

    try:
        _collect_completed_worker_futures(futures=futures, runner=runner)  # type: ignore[arg-type]
    except RuntimeError as exc:
        assert str(exc) == "database unavailable"
    else:
        raise AssertionError("release error was not propagated")

    assert futures == {future: ("work", "work-1", claimed_at)}
