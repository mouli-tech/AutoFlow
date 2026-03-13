from __future__ import annotations

import importlib
import logging
import pkgutil
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autoflow.actions.base import BaseAction

log = logging.getLogger(__name__)


class ActionRegistry:
    """Plugin registry with auto-discovery.

    Actions register themselves via the @register_action decorator.
    Discovery happens in three layers:

    1. Built-in actions: All modules in autoflow.actions are imported,
       triggering their @register_action decorators.
    2. Entry points: External packages can register actions via
       pyproject.toml [project.entry-points."autoflow.actions"]
    3. Manual: registry.register("name", ActionClass) still works.
    """

    _instance: ActionRegistry | None = None
    _actions: dict
    _discovered: bool
    _lock = threading.Lock()

    def __new__(cls) -> ActionRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._actions = {}
                    cls._instance._discovered = False
        return cls._instance

    def register(self, name: str, action_class: type[BaseAction]) -> None:
        """Register an action class under a name."""
        if name in self._actions and self._actions[name] is not action_class:
            log.warning("Overriding action '%s': %s -> %s", name, self._actions[name], action_class)
        self._actions[name] = action_class

    def get(self, name: str) -> type[BaseAction]:
        """Get an action class by name. Raises KeyError if not found."""
        if not self._discovered:
            self.discover()
        if name not in self._actions:
            available = ", ".join(sorted(self._actions.keys()))
            raise KeyError(f"Unknown action '{name}'. Available: {available}")
        return self._actions[name]

    def list_actions(self) -> list[str]:
        """List all registered action names."""
        if not self._discovered:
            self.discover()
        return sorted(self._actions.keys())

    def discover(self) -> None:
        """Run all discovery mechanisms. Safe to call multiple times."""
        if self._discovered:
            return
        self._discovered = True
        self._discover_builtins()
        self._discover_entry_points()
        log.info("Discovered %d actions: %s", len(self._actions), ", ".join(sorted(self._actions.keys())))

    def _discover_builtins(self) -> None:
        """Import all modules in autoflow.actions, triggering @register_action decorators."""
        import autoflow.actions as actions_pkg

        for importer, modname, ispkg in pkgutil.iter_modules(actions_pkg.__path__):
            if modname.startswith("_"):
                continue
            try:
                importlib.import_module(f"autoflow.actions.{modname}")
            except Exception as e:
                log.warning("Failed to load built-in action module '%s': %s", modname, e)

    def _discover_entry_points(self) -> None:
        """Discover actions from external packages via entry_points.

        External packages register actions in pyproject.toml:
            [project.entry-points."autoflow.actions"]
            my_action = "my_package.actions:MyAction"
        """
        try:
            from importlib.metadata import entry_points
        except ImportError:
            from importlib_metadata import entry_points

        try:
            eps = entry_points(group="autoflow.actions")
        except TypeError:
            # Python 3.9 compatibility
            eps = entry_points().get("autoflow.actions", [])

        for ep in eps:
            try:
                action_class = ep.load()
                self.register(ep.name, action_class)
                log.info("Loaded external action '%s' from %s", ep.name, ep.value)
            except Exception as e:
                log.warning("Failed to load entry point '%s': %s", ep.name, e)

    # Backward compatibility alias
    def discover_builtins(self) -> None:
        """Alias for discover(). Kept for backward compatibility."""
        self.discover()


registry = ActionRegistry()
