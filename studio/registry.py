"""Finds engine adapters by name. A class (not a global) so tests get a fresh one."""
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from studio import engines
from studio.engines.base import EngineAdapter

REQUIRED_ATTRIBUTES = ("name", "version", "profile")


class Registry:
    def __init__(self) -> None:
        self._adapters: dict[str, EngineAdapter] = {}

    def register(self, adapter: EngineAdapter) -> None:
        # ABC only enforces methods, so we check the attributes here.
        for attr in REQUIRED_ATTRIBUTES:
            if not getattr(adapter, attr, None):
                raise TypeError(f"adapter {type(adapter).__name__} must define '{attr}'")
        existing = self._adapters.get(adapter.name)
        if existing is adapter:
            return  # registering the same object twice is harmless
        if existing is not None:
            raise ValueError(f"an engine named '{adapter.name}' is already registered")
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> EngineAdapter:
        if name not in self._adapters:
            raise KeyError(f"unknown engine '{name}'; available: {self.names()}")
        return self._adapters[name]

    def names(self) -> list[str]:
        return sorted(self._adapters)

    def discover(self, package: ModuleType = engines) -> "Registry":
        """Import every module in the package and register its ADAPTER, if it has one."""
        for module_info in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"{package.__name__}.{module_info.name}")
            adapter = getattr(module, "ADAPTER", None)
            if adapter is not None:
                self.register(adapter)
        return self
