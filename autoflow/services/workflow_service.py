"""Unified WorkflowService — single source of truth for workflows.

YAML files are the primary storage. The SQLite database serves as a
cache/index for fast dashboard queries. Both CLI and API go through
this service, eliminating the sync gap.

Flow:
  YAML files (source of truth) → WorkflowService → SQLite (cache)
  CLI reads/writes YAML via service → service syncs to DB
  Dashboard reads/writes via API → API calls service → writes YAML + updates DB
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from autoflow.config import WORKFLOWS_DIR
from autoflow.engine.workflow import Workflow

log = logging.getLogger(__name__)


class WorkflowService:
    """Manages workflows with YAML as source of truth and DB as cache.

    This replaces the old pattern where CLI read YAML and dashboard read DB
    independently. Now both go through this service.
    """

    def __init__(self, workflows_dir: Path = WORKFLOWS_DIR, db_session_factory=None):
        self.workflows_dir = workflows_dir
        self._db_factory = db_session_factory
        self.workflows_dir.mkdir(parents=True, exist_ok=True)

    # ── CRUD operations ────────────────────────────────────────────

    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all workflows from YAML files."""
        results = []
        yaml_files = sorted(self.workflows_dir.glob("*.yaml")) + sorted(self.workflows_dir.glob("*.yml"))

        for f in yaml_files:
            try:
                wf = Workflow.from_yaml(f)
                results.append({
                    "name": wf.name,
                    "description": wf.description,
                    "trigger_type": wf.trigger.type if wf.trigger else "manual",
                    "enabled": wf.enabled,
                    "steps_count": len(wf.steps),
                    "source_file": f.name,
                    "definition": wf.to_dict(),
                })
            except Exception as e:
                log.warning("Failed to parse %s: %s", f, e)
                results.append({
                    "name": f.stem,
                    "description": "",
                    "trigger_type": "unknown",
                    "enabled": False,
                    "steps_count": 0,
                    "source_file": f.name,
                    "error": str(e),
                })

        return results

    def get_workflow(self, name: str) -> Optional[Workflow]:
        """Get a workflow by name from YAML files."""
        path = self._find_yaml(name)
        if path is None:
            return None
        return Workflow.from_yaml(path)

    def create_workflow(self, data: Dict[str, Any]) -> Workflow:
        """Create a new workflow, writing it to YAML."""
        wf = Workflow.from_dict(data)
        filename = self._slugify(wf.name) + ".yaml"
        path = self.workflows_dir / filename

        if path.exists():
            raise FileExistsError(f"Workflow file already exists: {filename}")

        wf.to_yaml(path)
        wf.source_path = str(path)

        # Sync to DB cache
        self._sync_to_db(wf, path)

        log.info("Created workflow '%s' at %s", wf.name, path)
        return wf

    def update_workflow(self, name: str, data: Dict[str, Any]) -> Workflow:
        """Update an existing workflow, rewriting its YAML file."""
        path = self._find_yaml(name)
        if path is None:
            raise FileNotFoundError(f"Workflow not found: {name}")

        # Load existing, merge updates
        existing = Workflow.from_yaml(path)
        merged = existing.to_dict()
        merged.update(data)

        wf = Workflow.from_dict(merged)

        # If name changed, rename the file
        new_filename = self._slugify(wf.name) + ".yaml"
        new_path = self.workflows_dir / new_filename
        if new_path != path:
            if new_path.exists():
                raise FileExistsError(f"Workflow file already exists: {new_filename}")
            path.unlink()
            path = new_path

        wf.to_yaml(path)
        wf.source_path = str(path)

        # Sync to DB cache
        self._sync_to_db(wf, path)

        log.info("Updated workflow '%s' at %s", wf.name, path)
        return wf

    def delete_workflow(self, name: str) -> bool:
        """Delete a workflow by removing its YAML file."""
        path = self._find_yaml(name)
        if path is None:
            return False

        path.unlink()

        # Remove from DB cache
        self._remove_from_db(name)

        log.info("Deleted workflow '%s'", name)
        return True

    def toggle_workflow(self, name: str) -> Optional[bool]:
        """Toggle a workflow's enabled state. Returns new state or None if not found."""
        path = self._find_yaml(name)
        if path is None:
            return None

        wf = Workflow.from_yaml(path)
        wf.enabled = not wf.enabled
        wf.to_yaml(path)

        self._sync_to_db(wf, path)
        return wf.enabled

    def run_workflow(self, name: str):
        """Load and execute a workflow. Returns ExecutionResult."""
        from autoflow.engine.executor import WorkflowExecutor

        wf = self.get_workflow(name)
        if wf is None:
            raise FileNotFoundError(f"Workflow not found: {name}")

        executor = WorkflowExecutor()
        return executor.execute(wf)

    # ── Sync: YAML → DB cache ─────────────────────────────────────

    def sync_all_to_db(self) -> int:
        """Sync all YAML workflows into the DB cache. Returns count synced."""
        if self._db_factory is None:
            return 0

        count = 0
        yaml_files = sorted(self.workflows_dir.glob("*.yaml")) + sorted(self.workflows_dir.glob("*.yml"))

        for f in yaml_files:
            try:
                wf = Workflow.from_yaml(f)
                self._sync_to_db(wf, f)
                count += 1
            except Exception as e:
                log.warning("Failed to sync %s: %s", f, e)

        return count

    def _sync_to_db(self, wf: Workflow, path: Path) -> None:
        """Upsert a single workflow into the DB cache."""
        if self._db_factory is None:
            return

        from autoflow.db.models import WorkflowModel

        session = self._db_factory()
        try:
            existing = session.query(WorkflowModel).filter(WorkflowModel.name == wf.name).first()
            if existing:
                existing.description = wf.description
                existing.definition = json.dumps(wf.to_dict())
                existing.trigger_type = wf.trigger.type if wf.trigger else "manual"
                existing.trigger_config = json.dumps(
                    {"cron": wf.trigger.cron, "interval_minutes": wf.trigger.interval_minutes}
                    if wf.trigger else {}
                )
                existing.enabled = wf.enabled
            else:
                model = WorkflowModel(
                    name=wf.name,
                    description=wf.description,
                    definition=json.dumps(wf.to_dict()),
                    trigger_type=wf.trigger.type if wf.trigger else "manual",
                    trigger_config=json.dumps(
                        {"cron": wf.trigger.cron, "interval_minutes": wf.trigger.interval_minutes}
                        if wf.trigger else {}
                    ),
                    enabled=wf.enabled,
                )
                session.add(model)
            session.commit()
        except Exception as e:
            log.warning("DB sync failed for '%s': %s", wf.name, e)
            session.rollback()
        finally:
            session.close()

    def _remove_from_db(self, name: str) -> None:
        """Remove a workflow from the DB cache."""
        if self._db_factory is None:
            return

        from autoflow.db.models import WorkflowModel

        session = self._db_factory()
        try:
            wf = session.query(WorkflowModel).filter(WorkflowModel.name == name).first()
            if wf:
                session.delete(wf)
                session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    # ── Helpers ────────────────────────────────────────────────────

    def _find_yaml(self, name: str) -> Optional[Path]:
        """Find a YAML file by workflow name or filename stem."""
        # Try exact filename match first
        for ext in (".yaml", ".yml"):
            path = self.workflows_dir / f"{name}{ext}"
            if path.exists():
                return path

        # Try slugified name
        slug = self._slugify(name)
        for ext in (".yaml", ".yml"):
            path = self.workflows_dir / f"{slug}{ext}"
            if path.exists():
                return path

        # Try matching by workflow name inside the YAML
        for f in self.workflows_dir.glob("*.yaml"):
            try:
                wf = Workflow.from_yaml(f)
                if wf.name == name:
                    return f
            except Exception:
                continue
        for f in self.workflows_dir.glob("*.yml"):
            try:
                wf = Workflow.from_yaml(f)
                if wf.name == name:
                    return f
            except Exception:
                continue

        return None

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a workflow name to a filename-safe slug."""
        return name.lower().replace(" ", "_").replace("-", "_")
