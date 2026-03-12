"""Typed execution context for workflow steps.

StepContext replaces the old pattern of stuffing _context, _executor, etc.
into the params dict. Actions receive a clean StepContext alongside their
user-defined params, keeping concerns separated.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from autoflow.engine.executor import WorkflowExecutor
    from autoflow.engine.workflow import WorkflowStep


@dataclass
class StepContext:
    """Immutable-ish context passed to every action during execution."""

    # Shared state across steps — actions can read/write here
    variables: Dict[str, Any] = field(default_factory=dict)

    # Logger scoped to this step
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("autoflow.step"))

    # Reference to the executor for nested execution (conditional, parallel)
    executor: Optional[WorkflowExecutor] = None

    # Name of the current workflow (for logging/context)
    workflow_name: str = ""

    # Current step index
    step_index: int = 0

    def get(self, key: str, default: Any = None) -> Any:
        """Get a variable from shared state."""
        return self.variables.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a variable in shared state."""
        self.variables[key] = value

    def update(self, data: Dict[str, Any]) -> None:
        """Merge a dict into shared state."""
        self.variables.update(data)

    def execute_nested_steps(self, steps: List[WorkflowStep]) -> list:
        """Execute nested steps using the parent executor.
        
        Used by conditional, parallel, and other meta-actions.
        Returns list of StepResult.
        """
        if self.executor is None:
            raise RuntimeError("No executor available for nested step execution")
        return self.executor.execute_steps(steps)
