from django.db import models
from django.utils import timezone

class ExtractionJob(models.Model):
	class Status(models.TextChoices):
		PENDING = "pending", "Pending"
		RUNNING = "running", "Running"
		DONE = "done", "Done"
		ERROR = "error", "Error"

	id = models.CharField(primary_key=True, max_length=32, editable=False)
	params = models.JSONField()
	output_dir = models.CharField(max_length=1024)
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
	error = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	started_at = models.DateTimeField(null=True, blank=True)
	finished_at = models.DateTimeField(null=True, blank=True)
	updated_at = models.DateTimeField(auto_now=True)
	total_steps = models.PositiveIntegerField(default=0)
	current_step = models.PositiveIntegerField(default=0)
	total_frames = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ("-created_at",)

	def __str__(self) -> str:
		return f"{self.id} ({self.status})"

	@property
	def percent(self) -> int:
		if self.total_steps:
			return int(self.current_step * 100 / max(1, self.total_steps))
		return 0

	@property
	def elapsed_seconds(self) -> float:
		start = self.started_at or self.created_at
		if not start:
			return 0.0
		end = self.finished_at or timezone.now()
		return max(0.0, (end - start).total_seconds())

	def status_css(self) -> str:
		return {
			self.Status.DONE: "done",
			self.Status.RUNNING: "running",
			self.Status.ERROR: "error",
		}.get(self.status, "pending")
