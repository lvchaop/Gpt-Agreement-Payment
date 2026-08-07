from __future__ import annotations

from refactor_app.plugins.contracts import (
    DownstreamProvider,
    HealthcheckResult,
    MailProvider,
    OpenAIChatGPTProvider,
    PluginContract,
    ProxyProvider,
)


class Plugin(PluginContract):
    def validate_config(self) -> None: ...

    def healthcheck(self) -> HealthcheckResult: ...

    def capabilities(self) -> list[str]: ...


__all__ = [
    "DownstreamProvider",
    "HealthcheckResult",
    "MailProvider",
    "OpenAIChatGPTProvider",
    "Plugin",
    "ProxyProvider",
]
