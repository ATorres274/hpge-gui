class ModuleRegistry:
    """Registry for tab modules. Allows each tab to have its own registry instance.

    Methods:
        - register(name, module)
        - get(name)
        - unregister(name)
        - list(): return list of registered names
    """

    def __init__(self) -> None:
        self._modules: dict[str, object] = {}

    def register(self, name: str, module: object) -> None:
        self._modules[name] = module

    def get(self, name: str) -> object | None:
        return self._modules.get(name)

    def unregister(self, name: str) -> None:
        if name in self._modules:
            del self._modules[name]

    # Alias to provide a consistent API with other registries
    def list(self) -> list[str]:
        return list(self._modules.keys())
