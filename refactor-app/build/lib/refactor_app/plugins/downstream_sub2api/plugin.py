from __future__ import annotations

from refactor_app.plugins.contracts import (
    DownstreamCodexPayload,
    DownstreamPushResult,
    HealthcheckResult,
)
from refactor_app.plugins.downstream_sub2api.client import Sub2ApiClient, Sub2ApiClientConfig


class Sub2ApiDownstreamPlugin:
    name = "downstream_sub2api"

    def __init__(self, client: Sub2ApiClient) -> None:
        self._client = client

    @classmethod
    def from_config(cls, config: Sub2ApiClientConfig) -> Sub2ApiDownstreamPlugin:
        return cls(Sub2ApiClient(config))

    def validate_config(self) -> None:
        return None

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok", details={"provider": "sub2api"})

    def capabilities(self) -> list[str]:
        return [
            "downstream.sub2api.push_codex_credential",
            "downstream.sub2api.push_business_access_token",
        ]

    def push_codex_credential(self, payload: DownstreamCodexPayload) -> DownstreamPushResult:
        return self._client.push_codex_credential(payload)

    def push_business_access_token(self, payload: dict) -> DownstreamPushResult:
        return self._client.push_business_access_token(payload)
