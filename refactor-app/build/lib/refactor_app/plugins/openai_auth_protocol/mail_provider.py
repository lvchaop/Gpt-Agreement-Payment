from __future__ import annotations

from typing import Protocol


class MailProvider(Protocol):
    def wait_for_otp(
        self,
        email: str,
        timeout: int = 180,
        issued_after: float | None = None,
        max_polls: int | None = None,
    ) -> str:
        ...
