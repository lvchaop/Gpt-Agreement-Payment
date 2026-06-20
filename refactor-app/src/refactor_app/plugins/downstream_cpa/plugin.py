from __future__ import annotations

from refactor_app.plugins.contracts import (
    DownstreamCodexPayload,
    DownstreamPushResult,
    HealthcheckResult,
)
from refactor_app.plugins.downstream_cpa.client import CpaClient, CpaClientConfig


class CpaDownstreamPlugin:
    name = "downstream_cpa"

    def __init__(self, client: CpaClient) -> None:
        self._client = client

    @classmethod
    def from_config(cls, config: CpaClientConfig) -> CpaDownstreamPlugin:
        return cls(CpaClient(config))

    def validate_config(self) -> None:
        return None

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok", details={"provider": "cpa"})

    def capabilities(self) -> list[str]:
        return ["downstream.cpa.push_codex_credential"]

    def push_codex_credential(self, payload: DownstreamCodexPayload) -> DownstreamPushResult:
        return self._client.push_codex_credential(payload)
