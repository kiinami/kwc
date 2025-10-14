from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from django.db import close_old_connections
from django.utils import timezone

from .extractor import ExtractParams, extract
from .models import ExtractionJob


logger = logging.getLogger(__name__)


class JobRunner:
	"""Manage extraction job execution and lifecycle in background threads."""

	FINISHED_STATUSES = frozenset({ExtractionJob.Status.DONE, ExtractionJob.Status.ERROR})

	def __init__(
		self,
		*,
		extractor: Callable[..., int] = extract,
		model: type[ExtractionJob] = ExtractionJob,
		thread_factory: Callable[[Callable[[str], None], tuple[str, ...]], threading.Thread] | None = None,
	) -> None:
		self.extractor = extractor
		self.model = model
		self._thread_factory = thread_factory
		self._threads: dict[str, threading.Thread] = {}
		self._lock = threading.Lock()
		self.finished_statuses = frozenset({model.Status.DONE, model.Status.ERROR})

	def start_job(self, job_id: str) -> None:
		"""Launch an extraction job in the background."""
		thread = self._make_thread(job_id)
		with self._lock:
			self._threads[job_id] = thread
		thread.start()

	def is_running(self, job_id: str) -> bool:
		with self._lock:
			return job_id in self._threads

	def mark_finished(self, job_id: str) -> None:
		with self._lock:
			self._threads.pop(job_id, None)

	def run_job(self, job_id: str) -> None:
		"""Execute an extraction job synchronously.

		Used as the thread target and directly in tests.
		"""
		try:
			with self.connection_guard():
				self._execute_job(job_id)
		finally:
			self.mark_finished(job_id)

	@contextmanager
	def connection_guard(self):
		"""Ensure database connections are reset around background work."""
		close_old_connections()
		try:
			yield
		finally:
			close_old_connections()

	def _make_thread(self, job_id: str) -> threading.Thread:
		factory = self._thread_factory or self._default_thread_factory
		return factory(self.run_job, (job_id,))

	@staticmethod
	def _default_thread_factory(target: Callable[[str], None], args: tuple[str, ...]) -> threading.Thread:
		return threading.Thread(target=target, args=args, daemon=True)

	def _execute_job(self, job_id: str) -> None:
		job = self._get_job(job_id)
		if job is None:
			return

		job.status = self.model.Status.RUNNING
		job.started_at = timezone.now()
		job.error = ""
		job.current_step = 0
		job.total_steps = 0
		job.total_frames = 0
		job.save(update_fields=["status", "started_at", "error", "current_step", "total_steps", "total_frames", "updated_at"])

		params_data = job.params or {}
		video_path = Path(params_data["video"])
		output_dir = Path(params_data.get("output_dir") or job.output_dir)
		trim_intervals = list(params_data.get("trim_intervals") or [])
		image_pattern = str(params_data.get("image_pattern") or "")

		extract_params = ExtractParams(
			video=video_path,
			output_dir=output_dir,
			trim_intervals=trim_intervals,
			title=str(params_data.get("title") or ""),
			image_pattern=image_pattern,
			year=int(params_data["year"]) if params_data.get("year") not in (None, "") else None,
			season=int(params_data["season"]) if params_data.get("season") not in (None, "") else None,
			episode=params_data.get("episode") if params_data.get("episode") not in (None, "") else None,
		)

		def on_progress(done: int, total: int) -> None:
			self.model.objects.filter(pk=job_id).update(
				total_steps=max(total, 1),
				current_step=done,
				total_frames=done,
				updated_at=timezone.now(),
			)

		try:
			frame_count = self.extractor(params=extract_params, on_progress=on_progress)
			job.refresh_from_db()
			job.total_frames = frame_count
			if job.total_steps == 0:
				job.total_steps = frame_count
			job.current_step = job.total_steps
			job.status = self.model.Status.DONE
			job.finished_at = timezone.now()
			job.save(update_fields=["status", "finished_at", "total_frames", "current_step", "total_steps", "updated_at"])
		except Exception as exc:  # pragma: no cover - defensive
			logger.exception("extract job %s failed", job_id)
			self.model.objects.filter(pk=job_id).update(
				status=self.model.Status.ERROR,
				error=str(exc),
				finished_at=timezone.now(),
				updated_at=timezone.now(),
			)

	def _get_job(self, job_id: str) -> ExtractionJob | None:
		try:
			return self.model.objects.get(pk=job_id)
		except self.model.DoesNotExist:
			return None


job_runner = JobRunner()
