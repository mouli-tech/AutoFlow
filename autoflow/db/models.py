from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class WorkflowModel(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, default="")
    definition = Column(Text, nullable=False)
    trigger_type = Column(String(50), default="manual")
    trigger_config = Column(Text, default="{}")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def get_definition(self) -> dict:
        return json.loads(self.definition) if self.definition else {}

    def set_definition(self, data: dict) -> None:
        self.definition = json.dumps(data)

    def get_trigger_config(self) -> dict:
        return json.loads(self.trigger_config) if self.trigger_config else {}

    def set_trigger_config(self, data: dict) -> None:
        self.trigger_config = json.dumps(data)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "definition": self.get_definition(), "trigger_type": self.trigger_type,
            "trigger_config": self.get_trigger_config(), "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ExecutionLogModel(Base):
    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, nullable=False)
    workflow_name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    step_results = Column(Text, default="[]")
    total_duration_ms = Column(Integer, default=0)

    def get_step_results(self) -> list:
        return json.loads(self.step_results) if self.step_results else []

    def set_step_results(self, data: list) -> None:
        self.step_results = json.dumps(data)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "workflow_id": self.workflow_id, "workflow_name": self.workflow_name,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "step_results": self.get_step_results(), "total_duration_ms": self.total_duration_ms,
        }
