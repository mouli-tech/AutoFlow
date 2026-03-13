from __future__ import annotations

import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from autoflow.api.database import get_db
from autoflow.db.models import ExecutionLogModel, WorkflowModel
from autoflow.engine.executor import WorkflowExecutor
from autoflow.engine.workflow import Workflow
from autoflow.api.routes.workflows import get_service

router = APIRouter(prefix="/api/workflows", tags=["execution"])


@router.post("/{workflow_name}/run")
def run_workflow(workflow_name: str, db: Session = Depends(get_db)):
    """Run a workflow by name (loads from YAML via WorkflowService)."""
    service = get_service()
    wf = service.get_workflow(workflow_name)
    if not wf:
        raise HTTPException(404, "Workflow not found")

    definition = wf.to_dict()
    wf_name = wf.name

    wf_model = db.query(WorkflowModel).filter(WorkflowModel.name == wf_name).first()
    wf_db_id = wf_model.id if wf_model else 0

    log_entry = ExecutionLogModel(
        workflow_id=wf_db_id,
        workflow_name=wf_name,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    log_id = log_entry.id

    def _run():
        from autoflow.api.database import get_session_factory
        session = get_session_factory()()
        try:
            workflow = Workflow.from_dict(definition)
            executor = WorkflowExecutor()
            result = executor.execute(workflow)

            entry = session.query(ExecutionLogModel).filter(ExecutionLogModel.id == log_id).first()
            if entry:
                entry.status = "success" if result.success else "failed"
                entry.finished_at = datetime.now(timezone.utc)
                entry.set_step_results([
                    {"step_name": s.step_name, "action": s.action, "success": s.success,
                     "message": s.message, "data": s.data, "duration_ms": s.duration_ms}
                    for s in result.step_results
                ])
                entry.total_duration_ms = int(result.total_duration_ms)
                session.commit()
        except Exception as e:
            entry = session.query(ExecutionLogModel).filter(ExecutionLogModel.id == log_id).first()
            if entry:
                entry.status = "failed"
                entry.finished_at = datetime.now(timezone.utc)
                entry.set_step_results([{"error": str(e)}])
                session.commit()
        finally:
            session.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"message": f"Started '{wf_name}'", "log_id": log_id}


@router.get("/{workflow_name}/status")
def workflow_status(workflow_name: str, db: Session = Depends(get_db)):
    """Get latest execution status for a workflow."""
    log_entry = (
        db.query(ExecutionLogModel)
        .filter(ExecutionLogModel.workflow_name == workflow_name)
        .order_by(ExecutionLogModel.started_at.desc())
        .first()
    )
    if not log_entry:
        return {"status": "never_run"}
    return log_entry.to_dict()
