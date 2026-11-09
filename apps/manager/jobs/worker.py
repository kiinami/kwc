from __future__ import annotations

import time
import traceback

from django.utils import timezone

from .models import Job
from .registry import get_handler

PROGRESS_INTERVAL = 1.0


class JobCancelled(Exception):
    """Cooperative cancellation requested by the user."""


class JobContext:
    def __init__(self, job: Job | None = None, *, interval: float = PROGRESS_INTERVAL) -> None:
        self.job = job
        self._interval = interval
        self._last_write = 0.0

    @classmethod
    def for_test(cls) -> JobContext:
        return cls(None)

    def progress(self, current: int, *, total: int | None = None, message: str = "") -> None:
        if self.job is None:
            return
        self.job.progress_current = current
        if total is not None:
            self.job.progress_total = total
        if message:
            self.job.message = message[:255]
        now = time.monotonic()
        if message or now - self._last_write >= self._interval:
            self.job.save(update_fields=["progress_current", "progress_total", "message"])
            self._last_write = now

    def check_cancelled(self) -> None:
        if self.job is None:
            return
        self.job.refresh_from_db(fields=["cancel_requested", "status"])
        if self.job.cancel_requested or self.job.status == Job.Status.CANCELLING:
            raise JobCancelled


def _execute(job: Job) -> None:
    job.status = Job.Status.RUNNING
    job.started_at = timezone.now()
    job.finished_at = None
    job.error = ""
    job.message = ""
    job.save(update_fields=["status", "started_at", "finished_at", "error", "message"])

    context = JobContext(job)
    handler = get_handler(job.kind)
    result: dict = {}
    try:
        if handler is None:
            raise LookupError(f"no handler registered for {job.kind!r}")
        raw = handler(job, context)
        result = raw if isinstance(raw, dict) else ({} if raw is None else {"result": raw})
        job.status = Job.Status.DONE
    except JobCancelled:
        job.status = Job.Status.CANCELLED
    except Exception:
        job.status = Job.Status.ERROR
        job.error = traceback.format_exc()
    finally:
        job.finished_at = timezone.now()
        job.result = result
        job.save(
            update_fields=[
                "status",
                "error",
                "result",
                "finished_at",
                "progress_current",
                "progress_total",
                "message",
            ]
        )


def run_worker(*, once: bool = False) -> None:
    Job.objects.filter(status=Job.Status.RUNNING).update(
        status=Job.Status.INTERRUPTED,
        finished_at=timezone.now(),
        message="worker restarted",
    )
    while True:
        job = Job.objects.filter(status=Job.Status.QUEUED).order_by("created_at", "id").first()
        if job is None:
            if once:
                return
            time.sleep(PROGRESS_INTERVAL)
            continue
        _execute(job)
        if once:
            return
