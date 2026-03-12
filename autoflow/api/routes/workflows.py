from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from autoflow.api.database import get_db
from autoflow.db.models import WorkflowModel
from autoflow.services.workflow_service import WorkflowService
from autoflow.config import WORKFLOWS_DIR

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

# Shared service instance (initialized with DB factory in app lifespan)
_service: Optional[WorkflowService] = None


def get_service() -> WorkflowService:
    """Get or create the WorkflowService singleton."""
    global _service
    if _service is None:
        from autoflow.api.database import get_session_factory
        _service = WorkflowService(
            workflows_dir=WORKFLOWS_DIR,
            db_session_factory=get_session_factory(),
        )
    return _service


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    definition: Dict[str, Any] = Field(default_factory=dict)
    trigger_type: str = "manual"
    trigger_config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    definition: Optional[Dict[str, Any]] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


@router.get("")
def list_workflows():
    """List all workflows from YAML source files."""
    service = get_service()
    workflows = service.list_workflows()
    return {"workflows": workflows}


@router.post("", status_code=201)
def create_workflow(body: WorkflowCreate):
    """Create a new workflow (writes YAML + syncs to DB)."""
    service = get_service()

    # Build the workflow definition from the API payload
    definition = body.definition or {}
    definition.setdefault("name", body.name)
    definition.setdefault("description", body.description)
    definition.setdefault("trigger", {"type": body.trigger_type, **(body.trigger_config or {})})
    definition.setdefault("enabled", body.enabled)
    if "steps" not in definition:
        definition["steps"] = []

    try:
        wf = service.create_workflow(definition)
        return wf.to_dict()
    except FileExistsError:
        raise HTTPException(409, f"Workflow '{body.name}' already exists")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{workflow_name}")
def get_workflow(workflow_name: str):
    """Get a workflow by name from YAML files."""
    service = get_service()
    wf = service.get_workflow(workflow_name)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf.to_dict()


@router.put("/{workflow_name}")
def update_workflow(workflow_name: str, body: WorkflowUpdate):
    """Update an existing workflow (rewrites YAML + syncs to DB)."""
    service = get_service()

    update_data = body.model_dump(exclude_none=True)
    # Map API fields to workflow definition fields
    if "trigger_type" in update_data or "trigger_config" in update_data:
        trigger = {"type": update_data.pop("trigger_type", "manual")}
        trigger.update(update_data.pop("trigger_config", {}))
        update_data["trigger"] = trigger

    try:
        wf = service.update_workflow(workflow_name, update_data)
        return wf.to_dict()
    except FileNotFoundError:
        raise HTTPException(404, "Workflow not found")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/{workflow_name}")
def delete_workflow(workflow_name: str):
    """Delete a workflow (removes YAML file + DB cache)."""
    service = get_service()
    if not service.delete_workflow(workflow_name):
        raise HTTPException(404, "Workflow not found")
    return {"message": f"Deleted '{workflow_name}'"}


@router.post("/{workflow_name}/toggle")
def toggle_workflow(workflow_name: str):
    """Toggle a workflow's enabled state."""
    service = get_service()
    new_state = service.toggle_workflow(workflow_name)
    if new_state is None:
        raise HTTPException(404, "Workflow not found")
    return {"name": workflow_name, "enabled": new_state}
