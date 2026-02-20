"""Registry for tab managers.

Provides a `TabRegistry` class and a module-level `registry` instance
pre-registered with the project's tab manager classes so the app can
instantiate tabs by name.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Type


class TabRegistry:
    """Simple registry to hold tab manager classes.

    Usage:
        registry.register("browser", BrowserTabManager)
        cls = registry.get("browser")
        inst = registry.create("browser", app, root, open_btn)
    """

    def __init__(self) -> None:
        self._tabs: Dict[str, Type[Any]] = {}

    def register(self, name: str, cls: Type[Any]) -> None:
        self._tabs[name] = cls

    def get(self, name: str) -> Type[Any] | None:
        return self._tabs.get(name)

    def unregister(self, name: str) -> None:
        if name in self._tabs:
            del self._tabs[name]

    def list_tabs(self) -> List[str]:
        return list(self._tabs.keys())

    # Alias to provide consistent API with other registries
    def list(self) -> List[str]:
        return self.list_tabs()

    def create(self, name: str, *args: Any, **kwargs: Any) -> Any:
        cls = self.get(name)
        if cls is None:
            raise KeyError(f"No tab registered under name: {name}")
        return cls(*args, **kwargs)


# Create a default registry and register known tab classes.
registry = TabRegistry()

try:
    # Import known tab classes and register them.
    from .browser_tab import BrowserTab
    from .histogram_tab import HistogramTab, HistogramPreviewRenderer
    from .batch_tab import BatchProcessingTab

    registry.register("browser", BrowserTab)
    registry.register("histogram_tab", HistogramTab)
    registry.register("histogram_renderer", HistogramPreviewRenderer)
    registry.register("batch", BatchProcessingTab)
except Exception:
    # Best-effort registration; avoid hard failure during imports.
    pass

__all__ = ["TabRegistry", "registry"]
