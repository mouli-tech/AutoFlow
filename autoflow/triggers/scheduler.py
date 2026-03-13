from __future__ import annotations

import logging
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)


class WorkflowScheduler:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()
        self._jobs: dict = {}

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def add_workflow(self, workflow_id: str, trigger_type: str, trigger_config: dict, callback: Callable) -> None:
        self.remove_workflow(workflow_id)

        if trigger_type == "cron":
            cron_expr = trigger_config.get("cron", "0 9 * * *")
            trigger = CronTrigger.from_crontab(cron_expr)
            job = self.scheduler.add_job(callback, trigger, id=workflow_id)
            self._jobs[workflow_id] = job.id

        elif trigger_type == "interval":
            minutes = trigger_config.get("interval_minutes", 30)
            trigger = IntervalTrigger(minutes=minutes)
            job = self.scheduler.add_job(callback, trigger, id=workflow_id)
            self._jobs[workflow_id] = job.id

        elif trigger_type == "login":
            # "login" trigger = run once when the autoflow daemon starts.
            # AutoFlow installs itself as an XDG autostart entry, so daemon
            # start effectively means "user logged in." Schedule as a one-shot
            # job with a short delay to allow startup to complete.
            from datetime import datetime, timedelta
            from apscheduler.triggers.date import DateTrigger
            run_at = datetime.now() + timedelta(seconds=5)
            job = self.scheduler.add_job(callback, DateTrigger(run_date=run_at), id=workflow_id)
            self._jobs[workflow_id] = job.id

        elif trigger_type == "manual":
            pass

    def remove_workflow(self, workflow_id: str) -> None:
        if workflow_id in self._jobs:
            try:
                self.scheduler.remove_job(self._jobs[workflow_id])
            except Exception:
                pass
            del self._jobs[workflow_id]

    def list_jobs(self) -> list:
        return [
            {"id": j.id, "next_run": str(j.next_run_time) if j.next_run_time else None, "trigger": str(j.trigger)}
            for j in self.scheduler.get_jobs()
        ]
