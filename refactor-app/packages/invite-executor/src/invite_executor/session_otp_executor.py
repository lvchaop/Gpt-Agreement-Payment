from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock, Thread
from uuid import uuid4

from invite_executor.execution_gate import (
    BatchExecutionAlreadyRunningError,
    BatchExecutionGate,
)
from invite_executor.models import (
    SessionOtpBatchRequest,
    SessionOtpBatchSummary,
    SessionOtpBatchView,
    SessionOtpResult,
    SessionOtpSubmitItem,
)
from invite_executor.session_otp_transport import (
    AsyncSessionOtpTransport,
    PreparedSessionOtp,
    direct_proxy_endpoint_id,
    prepare_session_otp,
)
from invite_executor.transport import WarmupReport

SessionOtpTransportFactory = Callable[[int], AsyncSessionOtpTransport]
_TERMINAL_STATUSES = {"succeeded", "partial", "failed"}


class SessionOtpBatchNotFoundError(LookupError):
    pass


class SessionOtpBatchAlreadyRunningError(RuntimeError):
    def __init__(self, *, batch_type: str, batch_id: str) -> None:
        super().__init__(f"{batch_type} batch already running: {batch_id}")
        self.batch_type = batch_type
        self.batch_id = batch_id


class SessionOtpBatchTooLargeError(ValueError):
    pass


@dataclass
class _SessionOtpBatchState:
    batch_id: str
    target_count: int
    status: str = "queued"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    connections_ready_at: datetime | None = None
    barrier_released_at: datetime | None = None
    finished_at: datetime | None = None
    prewarmed_connection_count: int = 0
    prewarm_rounds: int = 0
    prewarm_http_versions: list[int] = field(default_factory=list)
    prewarm_unique_local_ports: int = 0
    reuse_validated_connection_count: int = 0
    opened_during_reuse_validation: int = 0
    results: list[SessionOtpResult] = field(default_factory=list)

    def view(self) -> SessionOtpBatchView:
        results = sorted(self.results, key=lambda item: item.index)
        return SessionOtpBatchView(
            batch_id=self.batch_id,
            status=self.status,
            created_at=self.created_at,
            started_at=self.started_at,
            connections_ready_at=self.connections_ready_at,
            barrier_released_at=self.barrier_released_at,
            finished_at=self.finished_at,
            prewarmed_connection_count=self.prewarmed_connection_count,
            prewarm_rounds=self.prewarm_rounds,
            prewarm_http_versions=list(self.prewarm_http_versions),
            prewarm_unique_local_ports=self.prewarm_unique_local_ports,
            reuse_validated_connection_count=self.reuse_validated_connection_count,
            opened_during_reuse_validation=self.opened_during_reuse_validation,
            summary=SessionOtpBatchSummary(
                target_count=self.target_count,
                succeeded_count=sum(item.status == "succeeded" for item in results),
                failed_count=sum(item.status == "failed" for item in results),
                skipped_count=sum(item.status == "skipped" for item in results),
            ),
            results=[item.model_copy(deep=True) for item in results],
        )


class SessionOtpBatchManager:
    def __init__(
        self,
        *,
        transport_factory: SessionOtpTransportFactory,
        max_batch_size: int = 1000,
        default_barrier_timeout_s: float = 120.0,
        release_window_s: float = 2.0,
        result_ttl_s: int = 3600,
        execution_gate: BatchExecutionGate | None = None,
    ) -> None:
        self._transport_factory = transport_factory
        self._max_batch_size = max(1, int(max_batch_size))
        self._default_barrier_timeout_s = max(1.0, float(default_barrier_timeout_s))
        self._release_window_s = max(0.0, float(release_window_s))
        self._result_ttl = timedelta(seconds=max(60, int(result_ttl_s)))
        self._execution_gate = execution_gate or BatchExecutionGate()
        self._lock = Lock()
        self._batches: dict[str, _SessionOtpBatchState] = {}
        self._active_batch_id = ""

    @property
    def active_batch_id(self) -> str:
        with self._lock:
            return self._active_batch_id

    @property
    def execution_gate(self) -> BatchExecutionGate:
        return self._execution_gate

    def submit(self, request: SessionOtpBatchRequest) -> SessionOtpBatchView:
        if len(request.items) > self._max_batch_size:
            raise SessionOtpBatchTooLargeError(
                f"batch size {len(request.items)} exceeds maximum {self._max_batch_size}"
            )

        with self._lock:
            self._cleanup_locked(datetime.now(UTC))
            if self._active_batch_id:
                raise SessionOtpBatchAlreadyRunningError(
                    batch_type="session_otp",
                    batch_id=self._active_batch_id,
                )
            batch_id = str(uuid4())
            try:
                self._execution_gate.acquire(batch_type="session_otp", batch_id=batch_id)
            except BatchExecutionAlreadyRunningError as exc:
                raise SessionOtpBatchAlreadyRunningError(
                    batch_type=exc.active.batch_type,
                    batch_id=exc.active.batch_id,
                ) from exc
            self._batches[batch_id] = _SessionOtpBatchState(
                batch_id=batch_id,
                target_count=len(request.items),
            )
            self._active_batch_id = batch_id

        thread = Thread(
            target=self._run_batch,
            args=(batch_id, request),
            name=f"session-otp-batch-{batch_id[:8]}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            with self._lock:
                self._batches.pop(batch_id, None)
                if self._active_batch_id == batch_id:
                    self._active_batch_id = ""
            self._execution_gate.release(batch_type="session_otp", batch_id=batch_id)
            raise
        return self.get(batch_id)

    def get(self, batch_id: str) -> SessionOtpBatchView:
        with self._lock:
            self._cleanup_locked(datetime.now(UTC))
            state = self._batches.get(batch_id)
            if state is None:
                raise SessionOtpBatchNotFoundError(batch_id)
            return state.view()

    def _run_batch(self, batch_id: str, request: SessionOtpBatchRequest) -> None:
        with self._lock:
            state = self._batches[batch_id]
            state.status = "running"
            state.started_at = datetime.now(UTC)

        prepared: list[PreparedSessionOtp] = []
        results: list[SessionOtpResult] = []
        proxy_slots: dict[str, int] = {}
        for index, item in enumerate(request.items):
            proxy_url = item.proxy_url.get_secret_value()
            proxy_slot = proxy_slots.setdefault(proxy_url, len(proxy_slots) + 1)
            try:
                prepared.append(
                    prepare_session_otp(
                        index=index,
                        proxy_slot=proxy_slot,
                        item=item,
                    )
                )
            except Exception as exc:
                results.append(self._prepare_skip(index=index, item=item, error=exc))

        if not prepared:
            self._finish_batch(batch_id, results)
            return

        timeout_s = request.barrier_timeout_s or self._default_barrier_timeout_s
        try:
            submitted_results = asyncio.run(
                self._run_prepared_batch(
                    batch_id=batch_id,
                    prepared=prepared,
                    timeout_s=timeout_s,
                )
            )
        except Exception as exc:
            submitted_results = [
                self._stage_failure(item=item, stage="prewarm", error=exc)
                for item in prepared
            ]
        self._finish_batch(batch_id, [*results, *submitted_results])

    async def _run_prepared_batch(
        self,
        *,
        batch_id: str,
        prepared: list[PreparedSessionOtp],
        timeout_s: float,
    ) -> list[SessionOtpResult]:
        transport = self._transport_factory(len(prepared))
        try:
            try:
                warmup_report = await transport.prewarm(prepared)
            except Exception as exc:
                return [
                    self._stage_failure(item=item, stage="prewarm", error=exc)
                    for item in prepared
                ]

            expected_warmups = len(prepared) * warmup_report.rounds
            if (
                warmup_report.target_count != len(prepared)
                or warmup_report.completed_count < expected_warmups
            ):
                error = RuntimeError(
                    "connection prewarm report is incomplete: "
                    f"target={warmup_report.target_count}/{len(prepared)} "
                    f"completed={warmup_report.completed_count}/{expected_warmups}"
                )
                return [
                    self._stage_failure(item=item, stage="prewarm", error=error)
                    for item in prepared
                ]

            self._mark_connections_ready(batch_id, warmup_report)
            ready_event = asyncio.Event()
            release_epoch = asyncio.get_running_loop().create_future()
            ready_times: dict[int, datetime] = {}
            ready_count = 0

            async def run_one(
                item: PreparedSessionOtp,
                release_offset_s: float,
            ) -> SessionOtpResult:
                nonlocal ready_count
                ready_at = datetime.now(UTC)
                ready_times[item.index] = ready_at
                ready_count += 1
                if ready_count == len(prepared):
                    ready_event.set()
                released_at = await release_epoch
                delay_s = (released_at + release_offset_s) - asyncio.get_running_loop().time()
                if delay_s > 0:
                    await asyncio.sleep(delay_s)
                return await self._send_one(
                    prepared=item,
                    ready_at=ready_at,
                    transport=transport,
                )

            tasks = [
                asyncio.create_task(
                    run_one(
                        item,
                        _linear_release_offset_s(
                            position=position,
                            item_count=len(prepared),
                            release_window_s=self._release_window_s,
                        ),
                    )
                )
                for position, item in enumerate(prepared)
            ]
            try:
                await asyncio.wait_for(ready_event.wait(), timeout=timeout_s)
            except TimeoutError as exc:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                return [
                    self._stage_failure(
                        item=item,
                        stage="barrier",
                        error=exc,
                        error_message=f"memory barrier timed out after {timeout_s:g}s",
                        ready_at=ready_times.get(item.index),
                    )
                    for item in prepared
                ]

            self._mark_barrier_released(batch_id)
            release_epoch.set_result(asyncio.get_running_loop().time())
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            results: list[SessionOtpResult] = []
            for item, outcome in zip(prepared, outcomes, strict=True):
                if isinstance(outcome, SessionOtpResult):
                    results.append(outcome)
                    continue
                error = outcome if isinstance(outcome, Exception) else RuntimeError(str(outcome))
                results.append(
                    self._stage_failure(
                        item=item,
                        stage="request",
                        error=error,
                        ready_at=ready_times.get(item.index),
                    )
                )
            return results
        finally:
            try:
                await transport.close()
            except Exception:
                pass

    async def _send_one(
        self,
        *,
        prepared: PreparedSessionOtp,
        ready_at: datetime,
        transport: AsyncSessionOtpTransport,
    ) -> SessionOtpResult:
        request_started_at = datetime.now(UTC)
        endpoint_id = transport.proxy_endpoint_id(prepared)
        try:
            payload = await transport.send(prepared)
            finished_at = datetime.now(UTC)
            return SessionOtpResult(
                index=prepared.index,
                item_id=prepared.item_id,
                email=prepared.email,
                status="succeeded",
                stage="request",
                proxy_endpoint_id=endpoint_id,
                http_status=int(payload.get("http_status") or 200),
                ready_at=ready_at,
                request_started_at=request_started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(request_started_at, finished_at),
                snapshot_patch=dict(payload.get("snapshot_patch") or {}),
            )
        except Exception as exc:
            finished_at = datetime.now(UTC)
            return SessionOtpResult(
                index=prepared.index,
                item_id=prepared.item_id,
                email=prepared.email,
                status="failed",
                stage="request",
                proxy_endpoint_id=endpoint_id,
                http_status=int(getattr(exc, "http_status", 0) or 0),
                ready_at=ready_at,
                request_started_at=request_started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(request_started_at, finished_at),
                error_type=type(exc).__name__[:200],
                error_message=str(exc)[:2000],
            )

    def _prepare_skip(
        self,
        *,
        index: int,
        item: SessionOtpSubmitItem,
        error: Exception,
    ) -> SessionOtpResult:
        now = datetime.now(UTC)
        return SessionOtpResult(
            index=index,
            item_id=item.item_id,
            email=item.email,
            status="skipped",
            stage="prepare",
            proxy_endpoint_id=direct_proxy_endpoint_id(item.proxy_url.get_secret_value()),
            ready_at=now,
            finished_at=now,
            error_type=type(error).__name__[:200],
            error_message=str(error)[:2000],
        )

    def _stage_failure(
        self,
        *,
        item: PreparedSessionOtp,
        stage: str,
        error: Exception,
        error_message: str = "",
        ready_at: datetime | None = None,
    ) -> SessionOtpResult:
        now = datetime.now(UTC)
        return SessionOtpResult(
            index=item.index,
            item_id=item.item_id,
            email=item.email,
            status="failed",
            stage=stage,
            proxy_endpoint_id=item.proxy_assignment.endpoint_id,
            ready_at=ready_at or now,
            finished_at=now,
            error_type=type(error).__name__[:200],
            error_message=(error_message or str(error))[:2000],
        )

    def _mark_connections_ready(self, batch_id: str, report: WarmupReport) -> None:
        with self._lock:
            state = self._batches.get(batch_id)
            if state is not None:
                state.connections_ready_at = datetime.now(UTC)
                state.prewarmed_connection_count = report.target_count
                state.prewarm_rounds = report.rounds
                state.prewarm_http_versions = list(report.http_versions)
                state.prewarm_unique_local_ports = report.unique_local_ports
                state.reuse_validated_connection_count = report.reuse_validated_count
                state.opened_during_reuse_validation = report.opened_during_reuse_validation

    def _mark_barrier_released(self, batch_id: str) -> None:
        with self._lock:
            state = self._batches.get(batch_id)
            if state is not None:
                state.barrier_released_at = datetime.now(UTC)

    def _finish_batch(self, batch_id: str, results: list[SessionOtpResult]) -> None:
        with self._lock:
            state = self._batches[batch_id]
            state.results = results
            succeeded_count = sum(item.status == "succeeded" for item in results)
            if succeeded_count == len(results):
                state.status = "succeeded"
            elif succeeded_count == 0:
                state.status = "failed"
            else:
                state.status = "partial"
            state.finished_at = datetime.now(UTC)
            if self._active_batch_id == batch_id:
                self._active_batch_id = ""
        self._execution_gate.release(batch_type="session_otp", batch_id=batch_id)

    def _cleanup_locked(self, now: datetime) -> None:
        expired_ids = [
            batch_id
            for batch_id, state in self._batches.items()
            if state.status in _TERMINAL_STATUSES
            and state.finished_at is not None
            and state.finished_at + self._result_ttl < now
        ]
        for batch_id in expired_ids:
            self._batches.pop(batch_id, None)


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _linear_release_offset_s(
    *,
    position: int,
    item_count: int,
    release_window_s: float,
) -> float:
    if item_count <= 0 or position < 0 or position >= item_count:
        raise ValueError("position must reference an item in the batch")
    return max(0.0, float(release_window_s)) * position / item_count
