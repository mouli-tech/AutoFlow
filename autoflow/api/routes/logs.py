from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from autoflow.api.database import get_db
from autoflow.db.models import ExecutionLogModel

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
def list_logs(limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(ExecutionLogModel).order_by(ExecutionLogModel.started_at.desc()).limit(limit).all()
    return {"logs": [l.to_dict() for l in logs]}


@router.get("/{log_id}")
def get_log(log_id: int, db: Session = Depends(get_db)):
    entry = db.query(ExecutionLogModel).filter(ExecutionLogModel.id == log_id).first()
    if not entry:
        raise HTTPException(404, "Log not found")
    return entry.to_dict()


@router.delete("")
def clear_logs(db: Session = Depends(get_db)):
    count = db.query(ExecutionLogModel).delete()
    db.commit()
    return {"message": f"Cleared {count} log(s)"}
