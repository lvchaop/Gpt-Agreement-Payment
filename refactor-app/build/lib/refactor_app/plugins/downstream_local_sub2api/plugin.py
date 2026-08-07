from __future__ import annotations

from refactor_app.plugins.contracts import DownstreamCodexPayload, DownstreamPushResult, HealthcheckResult
from refactor_app.plugins.downstream_local_sub2api.client import (
    LocalSub2ApiClient,
    LocalSub2ApiClientConfig,
)


class LocalSub2ApiDownstreamPlugin:
    name = "downstream_local_sub2api"

    def __init__(self, client: LocalSub2ApiClient) -> None:
        self._client = client

    @classmethod
    def from_config(cls, config: LocalSub2ApiClientConfig) -> LocalSub2ApiDownstreamPlugin:
        return cls(LocalSub2ApiClient(config))

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok", details={"provider": "local_sub2api"})

    def capabilities(self) -> list[str]:
        return [
            "downstream.local_sub2api.push_codex_credential",
            "downstream.local_sub2api.push_business_access_token",
        ]

    def push_codex_credential(self, payload: DownstreamCodexPayload) -> DownstreamPushResult:
        return self._client.push_codex_credential(payload)

    def push_business_access_token(self, payload: dict) -> DownstreamPushResult:
        return self._client.push_business_access_token(payload)
