from __future__ import annotations

from refactor_app.plugins.contracts import DownstreamCodexPayload, DownstreamPushResult, HealthcheckResult
from refactor_app.plugins.downstream_custom_http.client import CustomHttpClient, CustomHttpClientConfig


class CustomHttpDownstreamPlugin:
    name = "downstream_custom_http"

    def __init__(self, client: CustomHttpClient) -> None:
        self._client = client

    @classmethod
    def from_config(cls, config: CustomHttpClientConfig) -> CustomHttpDownstreamPlugin:
        return cls(CustomHttpClient(config))

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok", details={"provider": "custom_http"})

    def capabilities(self) -> list[str]:
        return ["downstream.custom_http.push_codex_credential"]

    def push_codex_credential(self, payload: DownstreamCodexPayload) -> DownstreamPushResult:
        return self._client.push_codex_credential(payload)
