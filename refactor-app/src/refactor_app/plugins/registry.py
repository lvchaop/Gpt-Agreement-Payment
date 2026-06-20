from __future__ import annotations

from refactor_app.plugins.contracts import PluginContract


class PluginNotRegisteredError(KeyError):
    def __init__(self, name: str) -> None:
        super().__init__(f"plugin is not registered: {name}")


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginContract] = {}

    def register(self, name: str, plugin: PluginContract) -> None:
        plugin.validate_config()
        self._plugins[name] = plugin

    def get(self, name: str) -> PluginContract:
        try:
            return self._plugins[name]
        except KeyError as exc:
            raise PluginNotRegisteredError(name) from exc

    def require_capability(self, capability: str) -> PluginContract:
        for plugin in self._plugins.values():
            if capability in plugin.capabilities():
                return plugin
        raise PluginNotRegisteredError(capability)

    def names(self) -> list[str]:
        return sorted(self._plugins)
