from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock, Thread
from uuid import uuid4

from refactor_app.plugins.openai_chatgpt.client import prepare_invite_members_request

from invite_executor.execution_gate import (
    BatchExecutionAlreadyRunningError,
    BatchExecutionGate,
)
from invite_executor.models import (
    InviteBatchRequest,
    InviteBatchSummary,
    InviteBatchView,
    InviteResult,
)
from invite_executor.proxy_pool import StaticProxyAssignment
from invite_executor.transport import (
    AsyncInviteTransport,
    PreparedInvite,
    WarmupReport,
)

ProxyAllocator = Callable[[int], list[StaticProxyAssignment]]
TransportFactory = Callable[[int], AsyncInviteTransport]
_TERMINAL_STATUSES = {"succeeded", "partial", "failed"}


class InviteBatchNotFoundError(LookupError):
    pass


class InviteBatchAlreadyRunningError(RuntimeError):
    def __init__(self, batch_id: str, batch_type: str = "invite") -> None:
        super().__init__(f"{batch_type} batch already running: {batch_id}")
        self.batch_id = batch_id
        self.batch_type = batch_type


class InviteBatchTooLargeError(ValueError):
    pass


@dataclass
class _BatchState:
    batch_id: str
    external_space_id: str
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
    results: list[InviteResult] = field(default_factory=list)

    def view(self) -> InviteBatchView:
        results = sorted(self.results, key=lambda item: item.index)
        succeeded_count = sum(item.status == "succeeded" for item in results)
        failed_count = sum(item.status == "failed" for item in results)
        return InviteBatchView(
            batch_id=self.batch_id,
            external_space_id=self.external_space_id,
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
            summary=InviteBatchSummary(
                target_count=self.target_count,
                succeeded_count=succeeded_count,
                failed_count=failed_count,
            ),
            results=[item.model_copy(deep=True) for item in results],
        )


class InviteBatchManager:
    def __init__(
        self,
        *,
        max_batch_size: int = 1000,
        default_barrier_timeout_s: float = 30.0,
        release_interval_ms: float = 1.0,
        result_ttl_s: int = 3600,
        proxy_allocator: ProxyAllocator,
        transport_factory: TransportFactory,
        invite_proxy_count: int = 1000,
        execution_gate: BatchExecutionGate | None = None,
    ) -> None:
        self._max_batch_size = max(1, int(max_batch_size))
        self._default_barrier_timeout_s = max(1.0, float(default_barrier_timeout_s))
        self._release_interval_s = max(0.001, float(release_interval_ms) / 1000.0)
        self._result_ttl = timedelta(seconds=max(60, int(result_ttl_s)))
        self._proxy_allocator = proxy_allocator
        self._transport_factory = transport_factory
        self._invite_proxy_count = max(1, int(invite_proxy_count))
        self._lock = Lock()
        self._batches: dict[str, _BatchState] = {}
        self._active_batch_id = ""
        self._execution_gate = execution_gate or BatchExecutionGate()

    @property
    def active_batch_id(self) -> str:
        with self._lock:
            return self._active_batch_id

    @property
    def execution_gate(self) -> BatchExecutionGate:
        return self._execution_gate

    def submit(self, request: InviteBatchRequest) -> InviteBatchView:
        if len(request.emails) > self._max_batch_size:
            raise InviteBatchTooLargeError(
                f"batch size {len(request.emails)} exceeds maximum {self._max_batch_size}"
            )

        with self._lock:
            self._cleanup_locked(datetime.now(UTC))
            if self._active_batch_id:
                raise InviteBatchAlreadyRunningError(self._active_batch_id)
            batch_id = str(uuid4())
            try:
                self._execution_gate.acquire(batch_type="invite", batch_id=batch_id)
            except BatchExecutionAlreadyRunningError as exc:
                raise InviteBatchAlreadyRunningError(
                    exc.active.batch_id,
                    exc.active.batch_type,
                ) from exc
            state = _BatchState(
                batch_id=batch_id,
                external_space_id=request.external_space_id,
                target_count=len(request.emails),
            )
            self._batches[batch_id] = state
            self._active_batch_id = batch_id

        thread = Thread(
            target=self._run_batch,
            args=(batch_id, request),
            name=f"invite-batch-{batch_id[:8]}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            with self._lock:
                self._batches.pop(batch_id, None)
                if self._active_batch_id == batch_id:
                    self._active_batch_id = ""
            self._execution_gate.release(batch_type="invite", batch_id=batch_id)
            raise
        return self.get(batch_id)

    def get(self, batch_id: str) -> InviteBatchView:
        with self._lock:
            self._cleanup_locked(datetime.now(UTC))
            state = self._batches.get(batch_id)
            if state is None:
                raise InviteBatchNotFoundError(batch_id)
            return state.view()

    def _run_batch(self, batch_id: str, request: InviteBatchRequest) -> None:
        with self._lock:
            state = self._batches[batch_id]
            state.status = "running"
            state.started_at = datetime.now(UTC)

        target_count = len(request.emails)
        required_proxy_count = min(target_count, self._invite_proxy_count)
        proxy_indexes = [
            min((index * required_proxy_count) // target_count, required_proxy_count - 1)
            for index in range(target_count)
        ]
        try:
            proxy_assignments = self._proxy_allocator(required_proxy_count)
            if len(proxy_assignments) != required_proxy_count:
                raise RuntimeError(
                    f"proxy allocator returned {len(proxy_assignments)} endpoints; "
                    f"required {required_proxy_count}"
                )
            if any(not assignment.proxy_url.strip() for assignment in proxy_assignments):
                raise RuntimeError("proxy allocator returned an empty proxy URL")
        except Exception as exc:
            self._finish_batch(
                batch_id,
                [
                    self._proxy_failure(index=index, email=email, error=exc)
                    for index, email in enumerate(request.emails)
                ],
            )
            return

        timeout_s = request.barrier_timeout_s or self._default_barrier_timeout_s
        try:
            prepared = [
                PreparedInvite(
                    index=index,
                    email=email,
                    proxy_assignment=proxy_assignments[proxy_indexes[index]],
                    upstream=prepare_invite_members_request(
                        access_token=request.access_token.get_secret_value(),
                        team_id=request.external_space_id,
                        emails=[email],
                        cookie_header=request.cookie_header.get_secret_value(),
                    ),
                )
                for index, email in enumerate(request.emails)
            ]
        except Exception as exc:
            self._finish_batch(
                batch_id,
                [
                    self._stage_failure(
                        index=index,
                        email=email,
                        stage="prepare",
                        error=exc,
                        proxy_assignment=proxy_assignments[proxy_indexes[index]],
                    )
                    for index, email in enumerate(request.emails)
                ],
            )
            return

        try:
            results = asyncio.run(
                self._run_prepared_batch(
                    batch_id=batch_id,
                    prepared=prepared,
                    timeout_s=timeout_s,
                )
            )
        except Exception as exc:
            results = [
                self._stage_failure(
                    index=item.index,
                    email=item.email,
                    stage="prewarm",
                    error=exc,
                    proxy_assignment=item.proxy_assignment,
                )
                for item in prepared
            ]
        self._finish_batch(batch_id, results)

    async def _run_prepared_batch(
        self,
        *,
        batch_id: str,
        prepared: list[PreparedInvite],
        timeout_s: float,
    ) -> list[InviteResult]:
        transport = self._transport_factory(len(prepared))
        release_timer_handles: list[asyncio.TimerHandle] = []
        try:
            try:
                warmup_report = await transport.prewarm(prepared)
            except Exception as exc:
                return [
                    self._stage_failure(
                        index=item.index,
                        email=item.email,
                        stage="prewarm",
                        error=exc,
                        proxy_assignment=item.proxy_assignment,
                    )
                    for item in prepared
                ]

            expected_warmups = len(prepared) * warmup_report.rounds
            if (
                warmup_report.target_count != len(prepared)
                or warmup_report.completed_count < expected_warmups
            ):
                exc = RuntimeError(
                    "connection prewarm report is incomplete: "
                    f"target={warmup_report.target_count}/{len(prepared)} "
                    f"completed={warmup_report.completed_count}/{expected_warmups}"
                )
                return [
                    self._stage_failure(
                        index=item.index,
                        email=item.email,
                        stage="prewarm",
                        error=exc,
                        proxy_assignment=item.proxy_assignment,
                    )
                    for item in prepared
                ]

            self._mark_connections_ready(batch_id, warmup_report)
            ready_event = asyncio.Event()
            release_events = [asyncio.Event() for _item in prepared]
            ready_times: dict[int, datetime] = {}
            ready_count = 0

            async def run_one(
                item: PreparedInvite,
                release_event: asyncio.Event,
            ) -> InviteResult:
                nonlocal ready_count
                ready_at = datetime.now(UTC)
                ready_times[item.index] = ready_at
                ready_count += 1
                if ready_count == len(prepared):
                    ready_event.set()
                await release_event.wait()
                return await self._send_one(
                    prepared=item,
                    ready_at=ready_at,
                    transport=transport,
                )

            tasks = [
                asyncio.create_task(
                    run_one(
                        item,
                        release_events[position],
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
                        index=item.index,
                        email=item.email,
                        stage="barrier",
                        error=exc,
                        proxy_assignment=item.proxy_assignment,
                        error_message=f"memory barrier timed out after {timeout_s:g}s",
                        ready_at=ready_times.get(item.index),
                    )
                    for item in prepared
                ]

            self._mark_barrier_released(batch_id)
            _release_epoch, release_timer_handles = _arm_absolute_release_timers(
                release_events=release_events,
                interval_s=self._release_interval_s,
            )
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            results: list[InviteResult] = []
            for item, outcome in zip(prepared, outcomes, strict=True):
                if isinstance(outcome, InviteResult):
                    results.append(outcome)
                    continue
                error = outcome if isinstance(outcome, Exception) else RuntimeError(str(outcome))
                results.append(
                    self._stage_failure(
                        index=item.index,
                        email=item.email,
                        stage="request",
                        error=error,
                        proxy_assignment=item.proxy_assignment,
                        ready_at=ready_times.get(item.index),
                    )
                )
            return results
        finally:
            for handle in release_timer_handles:
                handle.cancel()
            try:
                await transport.close()
            except Exception:
                pass

    async def _send_one(
        self,
        *,
        prepared: PreparedInvite,
        ready_at: datetime,
        transport: AsyncInviteTransport,
    ) -> InviteResult:
        request_started_at = datetime.now(UTC)
        proxy_endpoint_id = _transport_proxy_endpoint_id(transport, prepared)
        try:
            payload = await transport.send(prepared)
            finished_at = datetime.now(UTC)
            return InviteResult(
                index=prepared.index,
                email=prepared.email,
                status="succeeded",
                stage="request",
                proxy_slot=prepared.proxy_assignment.slot,
                proxy_endpoint_id=proxy_endpoint_id,
                http_status=int(payload.get("http_status") or 200),
                ready_at=ready_at,
                request_started_at=request_started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(request_started_at, finished_at),
                payload=payload,
            )
        except Exception as exc:
            finished_at = datetime.now(UTC)
            return InviteResult(
                index=prepared.index,
                email=prepared.email,
                status="failed",
                stage="request",
                proxy_slot=prepared.proxy_assignment.slot,
                proxy_endpoint_id=proxy_endpoint_id,
                ready_at=ready_at,
                request_started_at=request_started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(request_started_at, finished_at),
                error_type=type(exc).__name__[:200],
                error_message=str(exc)[:2000],
            )

    def _proxy_failure(self, *, index: int, email: str, error: Exception) -> InviteResult:
        return self._stage_failure(
            index=index,
            email=email,
            stage="proxy",
            error=error,
        )

    def _stage_failure(
        self,
        *,
        index: int,
        email: str,
        stage: str,
        error: Exception,
        proxy_assignment: StaticProxyAssignment | None = None,
        error_message: str = "",
        ready_at: datetime | None = None,
    ) -> InviteResult:
        now = datetime.now(UTC)
        return InviteResult(
            index=index,
            email=email,
            status="failed",
            stage=stage,
            proxy_slot=proxy_assignment.slot if proxy_assignment is not None else 0,
            proxy_endpoint_id=(
                proxy_assignment.endpoint_id if proxy_assignment is not None else ""
            ),
            ready_at=ready_at or now,
            finished_at=now,
            error_type=type(error).__name__[:200],
            error_message=(error_message or str(error))[:2000],
        )

    def _finish_batch(self, batch_id: str, results: list[InviteResult]) -> None:
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
        self._execution_gate.release(batch_type="invite", batch_id=batch_id)

    def _mark_barrier_released(self, batch_id: str) -> None:
        with self._lock:
            state = self._batches.get(batch_id)
            if state is not None:
                state.barrier_released_at = datetime.now(UTC)

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


def _fixed_release_offset_s(*, position: int, interval_s: float) -> float:
    if position < 0:
        raise ValueError("position must be non-negative")
    return position * max(0.001, float(interval_s))


def _arm_absolute_release_timers(
    *,
    release_events: list[asyncio.Event],
    interval_s: float,
) -> tuple[float, list[asyncio.TimerHandle]]:
    loop = asyncio.get_running_loop()
    lead_s = max(0.01, len(release_events) * 0.00002)
    while True:
        release_epoch = loop.time() + lead_s
        handles = [
            loop.call_at(
                release_epoch
                + _fixed_release_offset_s(position=position, interval_s=interval_s),
                release_event.set,
            )
            for position, release_event in enumerate(release_events)
        ]
        if loop.time() < release_epoch:
            return release_epoch, handles
        for handle in handles:
            handle.cancel()
        lead_s *= 2


def _transport_proxy_endpoint_id(
    transport: AsyncInviteTransport,
    prepared: PreparedInvite,
) -> str:
    endpoint_id_getter = getattr(transport, "proxy_endpoint_id", None)
    if callable(endpoint_id_getter):
        endpoint_id = str(endpoint_id_getter(prepared) or "").strip()
        if endpoint_id:
            return endpoint_id
    return prepared.proxy_assignment.endpoint_id
