from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from .database import database_summary
from .services import analytics, rows


@dataclass(frozen=True)
class JobResult:
    name: str
    status: str
    detail: str


Job = Callable[[], JobResult]


def scheduled_lead_check() -> JobResult:
    open_tasks = rows("SELECT COUNT(*) AS count FROM follow_up_tasks WHERE status != 'Closed'")[0]["count"]
    return JobResult("scheduled_lead_check", "ready", f"{open_tasks} open follow-up tasks queued")


def daily_report_job() -> JobResult:
    data = analytics()
    return JobResult("daily_report", "ready", f"{data['daily_lead_count']} leads, {data['follow_up_queue']} open tasks")


def reminder_job() -> JobResult:
    due = (date.today() + timedelta(days=1)).isoformat()
    count = rows(
        "SELECT COUNT(*) AS count FROM follow_up_tasks WHERE due_date <= ? AND status != 'Closed'",
        (due,),
    )[0]["count"]
    return JobResult("task_reminders", "ready", f"{count} tasks due by {due}")


JOBS: list[Job] = [scheduled_lead_check, daily_report_job, reminder_job]


def run_registered_jobs() -> list[dict]:
    return [job().__dict__ for job in JOBS]


def scheduler_status() -> dict:
    return {
        "mode": "local-in-process",
        "database": database_summary(),
        "jobs": [job().__dict__ for job in JOBS],
        "celery_ready": True,
    }
