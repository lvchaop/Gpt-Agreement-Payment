from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class ActiveBatch:
    batch_type: str
    batch_id: str


class BatchExecutionAlreadyRunningError(RuntimeError):
    def __init__(self, active: ActiveBatch) -> None:
        super().__init__(f"{active.batch_type} batch already running: {active.batch_id}")
        self.active = active


class BatchExecutionGate:
    def __init__(self) -> None:
        self._lock = Lock()
        self._active: ActiveBatch | None = None

    @property
    def active(self) -> ActiveBatch | None:
        with self._lock:
            return self._active

    def acquire(self, *, batch_type: str, batch_id: str) -> None:
        with self._lock:
            if self._active is not None:
                raise BatchExecutionAlreadyRunningError(self._active)
            self._active = ActiveBatch(batch_type=batch_type, batch_id=batch_id)

    def release(self, *, batch_type: str, batch_id: str) -> None:
        with self._lock:
            if self._active == ActiveBatch(batch_type=batch_type, batch_id=batch_id):
                self._active = None
