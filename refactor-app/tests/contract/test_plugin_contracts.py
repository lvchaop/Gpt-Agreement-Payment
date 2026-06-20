from __future__ import annotations

from dataclasses import dataclass

import pytest

from refactor_app.plugins.contracts import HealthcheckResult
from refactor_app.plugins.registry import PluginNotRegisteredError, PluginRegistry
from refactor_app.ports.plugins import Plugin


@dataclass
class DummyPlugin:
    name: str = "dummy"
    validated: bool = False

    def validate_config(self) -> None:
        self.validated = True

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok")

    def capabilities(self) -> list[str]:
        return ["dummy.run"]


def assert_plugin_contract(plugin: Plugin) -> None:
    plugin.validate_config()
    health = plugin.healthcheck()
    assert health.status == "ok"
    assert "dummy.run" in plugin.capabilities()


def test_plugin_protocol_and_registry() -> None:
    plugin = DummyPlugin()
    assert_plugin_contract(plugin)

    registry = PluginRegistry()
    registry.register(plugin.name, plugin)

    assert plugin.validated is True
    assert registry.names() == ["dummy"]
    assert registry.get("dummy") is plugin
    assert registry.require_capability("dummy.run") is plugin


def test_registry_reports_missing_plugin() -> None:
    registry = PluginRegistry()

    with pytest.raises(PluginNotRegisteredError):
        registry.get("missing")
