from __future__ import annotations

from refactor_app.plugins.contracts import HealthcheckResult, ProxyNode
from refactor_app.plugins.proxy_webshare.client import WebshareClient, WebshareClientConfig


class WebshareProxyPlugin:
    name = "proxy_webshare"

    def __init__(self, client: WebshareClient) -> None:
        self._client = client

    @classmethod
    def from_config(cls, config: WebshareClientConfig) -> WebshareProxyPlugin:
        return cls(WebshareClient(config))

    def validate_config(self) -> None:
        return None

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok", details={"provider": "webshare"})

    def capabilities(self) -> list[str]:
        return [
            "ops.proxy.fetch_webshare_pool",
            "ops.proxy.refresh_webshare_pool",
        ]

    def list_proxies(self) -> list[ProxyNode]:
        return self._client.list_proxy_nodes()
