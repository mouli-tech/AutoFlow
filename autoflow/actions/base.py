from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from autoflow.engine.context import StepContext


@dataclass
class ActionResult:
    success: bool
    message: str = ""
    data: dict = field(default_factory=dict)


class BaseAction(ABC):
    """Base class for all workflow actions.

    Actions implement execute() which receives:
    - params: User-defined parameters from the YAML step config
    - context: Typed StepContext with shared state, logger, and executor ref

    For backward compatibility, context is optional — old actions that only
    accept params will still work.
    """

    @abstractmethod
    def execute(self, params: dict, context: Optional[StepContext] = None) -> ActionResult:
        ...


def register_action(name: str):
    """Decorator to auto-register an action class with the registry.

    Usage:
        @register_action("open_app")
        class OpenAppAction(BaseAction):
            def execute(self, params, context=None):
                ...

    The class is registered when the module is imported, which happens
    automatically during plugin discovery.
    """
    def decorator(cls):
        from autoflow.engine.registry import registry
        registry.register(name, cls)
        cls._action_name = name
        return cls
    return decorator
