import json
import uuid

from django.db import models


class Job(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        CANCELLING = "cancelling", "Cancelling"
        CANCELLED = "cancelled", "Cancelled"
        DONE = "done", "Done"
        ERROR = "error", "Error"
        INTERRUPTED = "interrupted", "Interrupted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=64)
    params = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    progress_current = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(null=True, blank=True)
    message = models.CharField(max_length=255, blank=True, default="")
    error = models.TextField(blank=True, default="")
    result = models.JSONField(default=dict, blank=True)
    cancel_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.kind} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status in {self.Status.QUEUED, self.Status.RUNNING, self.Status.CANCELLING}

    @property
    def percent(self) -> int:
        if not self.progress_total:
            return 0
        return min(100, int(self.progress_current * 100 / max(1, self.progress_total)))

    @property
    def params_pretty(self) -> str:
        return json.dumps(self.params, indent=2, default=str)

    @property
    def result_pretty(self) -> str:
        return json.dumps(self.result, indent=2, default=str)


def enqueue(kind: str, params: dict) -> Job:
    return Job.objects.create(kind=kind, params=params)
