from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    """A single step in a workflow.

    Enhanced with:
    - retry/retry_delay: automatic retry on failure
    - timeout: step-level timeout in seconds
    - parallel: list of sub-steps to run concurrently
    - depends_on: DAG-style dependency on other step names
    """

    action: str = ""
    params: Dict[str, Any] = Field(default_factory=dict)
    name: Optional[str] = None
    on_failure: str = "continue"  # "continue" | "stop"

    # Conditional fields
    condition: Optional[str] = None
    then: Optional[List[WorkflowStep]] = None
    else_steps: Optional[List[WorkflowStep]] = Field(default=None, alias="else")

    # New: retry support
    retry: int = 0  # number of retries (0 = no retry)
    retry_delay: float = 1.0  # seconds between retries

    # New: step-level timeout (seconds, 0 = no timeout)
    timeout: int = 0

    # New: parallel execution — if set, this step runs sub-steps concurrently
    parallel: Optional[List[WorkflowStep]] = None

    # New: DAG dependency — wait for named steps to complete before running
    depends_on: Optional[List[str]] = None

    class Config:
        populate_by_name = True

    def to_step_config(self) -> dict:
        """Extract step-level config for middleware (retry, timeout, etc.)."""
        return {
            "name": self.name or self.action,
            "action": self.action,
            "retry": self.retry,
            "retry_delay": self.retry_delay,
            "timeout": self.timeout,
            "on_failure": self.on_failure,
        }


class TriggerConfig(BaseModel):
    type: str
    cron: Optional[str] = None
    interval_minutes: Optional[int] = None


class Workflow(BaseModel):
    """A workflow definition.

    Enhanced with:
    - variables: workflow-level variables accessible to all steps
    - source_path: tracks which YAML file this came from
    """

    name: str
    description: str = ""
    trigger: TriggerConfig = Field(default_factory=lambda: TriggerConfig(type="manual"))
    steps: List[WorkflowStep] = Field(default_factory=list)
    enabled: bool = True

    # New: workflow-level variables (pre-populated into StepContext)
    variables: Dict[str, Any] = Field(default_factory=dict)

    # New: track source file (not serialized to YAML)
    source_path: Optional[str] = Field(default=None, exclude=True)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Workflow:
        path = Path(path)
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        wf = cls.model_validate(data)
        wf.source_path = str(path)
        return wf

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Workflow:
        return cls.model_validate(data)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True, exclude={"source_path"})

    def to_yaml(self, path: str | Path) -> None:
        """Serialize workflow back to a YAML file."""
        path = Path(path)
        data = self.to_dict()
        with open(path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
