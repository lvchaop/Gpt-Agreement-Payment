from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, Lock, Thread

from invite_executor.execution_gate import BatchExecutionAlreadyRunningError
from invite_executor.replenishment_engine import SpaceReplenishmentEngine
from invite_executor.replenishment_models import (
    ReplenishmentRegistration,
    ReplenishmentRunView,
    SpaceCycleResult,
    SpaceReplenishmentConfig,
    SpaceRuntimeView,
)
from invite_executor.replenishment_registry import ReplenishmentRegistry

logger = logging.getLogger(__name__)


@dataclass
class _RuntimeState:
    state: str = "idle"
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_result: SpaceCycleResult | None = None


class SpaceReplenishmentManager:
    def __init__(
        self,
        *,
        spaces: tuple[SpaceReplenishmentConfig, ...],
        engine: SpaceReplenishmentEngine,
        registry: ReplenishmentRegistry | None = None,
        interval_s: float = 120.0,
        max_workers: int = 20,
    ) -> None:
        self._spaces = {space.external_space_id: space for space in spaces}
        self._engine = engine
        self._registry = registry
        self._interval_s = max(1.0, float(interval_s))
        self._guard = Lock()
        self._registry_mutation_guard = Lock()
        self._states = {space_id: _RuntimeState() for space_id in self._spaces}
        self._stop_event = Event()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="space-replenish",
        )
        self._scheduler: Thread | None = None
        self._startup_state = "idle"
        self._startup_error = ""

    @property
    def interval_s(self) -> float:
        return self._interval_s

    @property
    def configured_space_count(self) -> int:
        with self._guard:
            return len(self._spaces)

    @property
    def startup_state(self) -> str:
        with self._guard:
            return self._startup_state

    @property
    def startup_error(self) -> str:
        with self._guard:
            return self._startup_error

    def register_space(
        self,
        *,
        external_space_id: str,
        registration: ReplenishmentRegistration,
        access_token: str,
        cookie_header: str,
    ) -> SpaceRuntimeView:
        if self._registry is None:
            raise RuntimeError("dynamic replenishment registry is not configured")
        with self._registry_mutation_guard:
            space = self._registry.register_from_invitation(
                external_space_id=external_space_id,
                registration=registration,
                access_token=access_token,
                cookie_header=cookie_header,
            )
            with self._guard:
                self._spaces[space.external_space_id] = space
                runtime = self._states.setdefault(space.external_space_id, _RuntimeState())
                return self._runtime_view_locked(space, runtime)

    def remove_space(self, external_space_id: str) -> bool:
        if self._registry is None:
            raise RuntimeError("dynamic replenishment registry is not configured")
        space_id = str(external_space_id or "").strip()
        with self._registry_mutation_guard:
            with self._guard:
                state = self._states.get(space_id)
                if state is not None and state.state in {"queued", "running"}:
                    raise RuntimeError("space_cycle_already_active")
                removed = self._registry.remove_space(space_id)
                if not removed:
                    return False
                self._spaces.pop(space_id, None)
                self._states.pop(space_id, None)
                return True

    def start(self) -> None:
        with self._guard:
            if self._scheduler is not None and self._scheduler.is_alive():
                return
            self._stop_event.clear()
            self._startup_state = "preparing"
            self._startup_error = ""
            self._scheduler = Thread(
                target=self._prepare_and_scheduler_loop,
                name="space-replenishment-bootstrap",
                daemon=True,
            )
            self._scheduler.start()

    def stop(self) -> None:
        self._stop_event.set()
        scheduler = self._scheduler
        if scheduler is not None:
            scheduler.join(timeout=min(5.0, self._interval_s + 1.0))
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._engine.close()

    def trigger(self, external_space_id: str) -> ReplenishmentRunView:
        space_id = str(external_space_id or "").strip()
        with self._guard:
            space = self._spaces.get(space_id)
            if space is None or not space.enabled:
                return ReplenishmentRunView(
                    accepted=False,
                    external_space_id=space_id,
                    reason="space_not_configured_or_disabled",
                )
            if self._startup_state in {"preparing", "failed"}:
                return ReplenishmentRunView(
                    accepted=False,
                    external_space_id=space_id,
                    reason=f"replenishment_not_ready:{self._startup_state}",
                )
            state = self._states[space_id]
            if state.state in {"queued", "running"}:
                return ReplenishmentRunView(
                    accepted=False,
                    external_space_id=space_id,
                    reason="space_cycle_already_active",
                )
            state.state = "queued"
            self._executor.submit(self._execute_space, space)
        return ReplenishmentRunView(
            accepted=True,
            external_space_id=space_id,
            reason="queued",
        )

    def status(self) -> list[SpaceRuntimeView]:
        with self._guard:
            return [
                self._runtime_view_locked(space, self._states[space.external_space_id])
                for space in sorted(
                    self._spaces.values(), key=lambda item: item.external_space_id
                )
            ]

    def active_space_count(self) -> int:
        with self._guard:
            return sum(
                state.state in {"queued", "running"} for state in self._states.values()
            )

    def _prepare_and_scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                prepare = getattr(self._engine, "prepare", None)
                if callable(prepare):
                    prepare()
            except BatchExecutionAlreadyRunningError as exc:
                with self._guard:
                    self._startup_state = "preparing"
                    self._startup_error = (
                        f"execution_gate_busy:{exc.active.batch_type}:{exc.active.batch_id}"
                    )
                logger.info(
                    "space replenishment runtime preparation deferred: "
                    "active_batch_type=%s active_batch_id=%s",
                    exc.active.batch_type,
                    exc.active.batch_id,
                )
                if self._stop_event.wait(min(5.0, self._interval_s)):
                    return
                continue
            except Exception as exc:
                with self._guard:
                    self._startup_state = "failed"
                    self._startup_error = f"{type(exc).__name__}: {exc}"[:1000]
                logger.exception("space replenishment runtime preparation failed")
                if self._stop_event.wait(min(30.0, self._interval_s)):
                    return
                with self._guard:
                    self._startup_state = "preparing"
                continue
            with self._guard:
                self._startup_state = "ready"
                self._startup_error = ""
            logger.info("space replenishment runtime is ready")
            self._scheduler_loop()
            return

    def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._guard:
                space_ids = tuple(
                    space_id
                    for space_id, space in self._spaces.items()
                    if space.enabled
                )
            for space_id in space_ids:
                self.trigger(space_id)
            self._stop_event.wait(self._interval_s)

    def _execute_space(self, space: SpaceReplenishmentConfig) -> None:
        started_at = datetime.now(UTC)
        with self._guard:
            state = self._states[space.external_space_id]
            state.state = "running"
            state.last_started_at = started_at
        logger.info(
            "space replenishment cycle started: external_space_id=%s",
            space.external_space_id,
        )
        try:
            result = self._engine.run(space)
        except Exception as exc:
            finished_at = datetime.now(UTC)
            result = SpaceCycleResult(
                external_space_id=space.external_space_id,
                status="failed",
                action="cycle",
                reason="unhandled_engine_error",
                error_type=type(exc).__name__,
                error_message=str(exc)[:1000],
                started_at=started_at,
                finished_at=finished_at,
            )
        with self._guard:
            state = self._states[space.external_space_id]
            state.state = "idle"
            state.last_finished_at = result.finished_at
            state.last_result = result
        logger.info(
            "space replenishment cycle finished: external_space_id=%s status=%s "
            "action=%s reason=%s",
            space.external_space_id,
            result.status,
            result.action,
            result.reason,
        )

    @staticmethod
    def _runtime_view_locked(
        space: SpaceReplenishmentConfig,
        state: _RuntimeState,
    ) -> SpaceRuntimeView:
        return SpaceRuntimeView(
            external_space_id=space.external_space_id,
            name=space.name,
            enabled=space.enabled,
            credential_type=space.credential_type,
            seat_limit=space.seat_limit,
            admin_key=space.admin_key,
            admin_email=space.admin_email,
            state=state.state,
            last_started_at=state.last_started_at,
            last_finished_at=state.last_finished_at,
            last_result=state.last_result,
        )
