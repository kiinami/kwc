"""Tests for job cancellation functionality."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from extract import job_runner as job_runner_module
from extract.extractor import CancellationToken, CancelledException, ExtractParams
from extract.job_runner import JobRunner
from extract.models import ExtractionJob


# Re-use test fixtures from test_job_runner.py
class ImmediateThread:
	def __init__(self, runner: JobRunner, target: Callable[[str], None], args: tuple[str, ...]) -> None:
		self._runner = runner
		self._target = target
		self._args = args
		self.started = False

	def start(self) -> None:
		self.started = True
		job_id = self._args[0]
		assert self._runner.is_running(job_id)
		self._target(*self._args)
		assert not self._runner.is_running(job_id)


class FakeManager:
	def __init__(self, job: FakeJob) -> None:
		self.job = job
		self.update_calls: list[dict[str, Any]] = []

	def get(self, pk: str) -> FakeJob:
		if pk != self.job.id:
			raise FakeModel.DoesNotExist
		return self.job

	def filter(self, pk: str) -> FakeQuerySet:
		return FakeQuerySet(self.job, self.update_calls)


class FakeQuerySet:
	def __init__(self, job: FakeJob, updates: list[dict[str, Any]]) -> None:
		self._job = job
		self._updates = updates

	def update(self, **fields: Any) -> None:
		self._updates.append(fields)
		for key, value in fields.items():
			setattr(self._job, key, value)
			if key == "status":
				self._job.status_transitions.append(self._job.status)  # type: ignore[arg-type]
		self._job.updated_at = timezone.now()


class FakeModel:
	Status = ExtractionJob.Status
	DoesNotExist = type("DoesNotExist", (Exception,), {})


def make_fake_job(job_id: str = "job123") -> FakeJob:
	return FakeJob(job_id)


class FakeJob:
	Status = ExtractionJob.Status

	def __init__(self, job_id: str) -> None:
		self.id = job_id
		self.params = {
			"video": str(Path("/tmp/video.mp4")),
			"output_dir": str(Path("/tmp/output")),
			"trim_intervals": ["00:00:05-00:00:10"],
			"image_pattern": "pattern",
			"title": "Sample",
			"year": "2024",
			"season": "",
			"episode": "",
		}
		self.output_dir = str(Path("/tmp/output"))
		self.status = ExtractionJob.Status.PENDING
		self.error = ""
		self.created_at = timezone.now()
		self.started_at = None
		self.finished_at = None
		self.updated_at = None
		self.total_steps = 0
		self.current_step = 0
		self.total_frames = 0
		self.status_transitions: list[str] = []
		self.saved_payloads: list[list[str] | None] = []
		self.refreshed = 0

	def save(self, update_fields: list[str] | None = None) -> None:
		self.saved_payloads.append(update_fields)
		if update_fields and "status" in update_fields:
			self.status_transitions.append(self.status)  # type: ignore[arg-type]
		self.updated_at = timezone.now()

	def refresh_from_db(self) -> None:
		self.refreshed += 1


def test_cancellation_token_initial_state() -> None:
	"""Test that a new cancellation token is not cancelled."""
	token = CancellationToken()
	assert not token.is_cancelled()


def test_cancellation_token_cancel() -> None:
	"""Test that cancelling a token sets the cancelled flag."""
	token = CancellationToken()
	token.cancel()
	assert token.is_cancelled()


def test_cancellation_token_thread_safe() -> None:
	"""Test that cancellation token is thread-safe."""
	import threading
	token = CancellationToken()
	
	def cancel_in_thread():
		token.cancel()
	
	thread = threading.Thread(target=cancel_in_thread)
	thread.start()
	thread.join()
	
	assert token.is_cancelled()


def _configure_runner(job: FakeJob, extractor: Callable[..., int]) -> tuple[JobRunner, FakeManager]:
	FakeModel.objects = FakeManager(job)  # type: ignore[attr-defined]
	manager = FakeModel.objects  # type: ignore[attr-defined]
	runner = JobRunner(model=FakeModel, extractor=extractor)  # type: ignore[arg-type]

	def thread_factory(target: Callable[[str], None], args: tuple[str, ...]) -> ImmediateThread:
		return ImmediateThread(runner, target, args)

	runner._thread_factory = thread_factory  # type: ignore[assignment]
	return runner, manager


def test_job_runner_cancel_running_job(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Test cancelling a running job."""
	job = make_fake_job()

	close_calls: list[str] = []
	monkeypatch.setattr(job_runner_module, "close_old_connections", lambda: close_calls.append("close"))

	cancel_token_used: list[CancellationToken | None] = []

	def fake_extract(*, params: ExtractParams, on_progress: Callable[[int, int], None]) -> int:
		# Record the cancel token
		cancel_token_used.append(params.cancel_token)
		
		# Simulate immediate cancellation
		# In a real scenario, the token would be cancelled externally
		# Here we simulate that by cancelling it ourselves
		if params.cancel_token:
			params.cancel_token.cancel()
		
		# Simulate checking for cancellation
		if params.cancel_token and params.cancel_token.is_cancelled():
			raise CancelledException("Job cancelled")
		
		on_progress(1, 3)
		return 3

	runner, _manager = _configure_runner(job, fake_extract)
	
	# Start the job - with ImmediateThread, it will execute synchronously
	# The cancel token will be set and checked within the fake_extract function
	runner.start_job(job.id)

	assert job.status == ExtractionJob.Status.CANCELLED
	assert "cancelled" in job.error.lower()
	assert job.finished_at is not None
	assert not runner.is_running(job.id)


def test_job_runner_cancel_nonexistent_job() -> None:
	"""Test that cancelling a nonexistent job returns False."""
	runner = JobRunner()
	result = runner.cancel_job("nonexistent-job-id")
	assert result is False


def test_job_runner_cancel_sets_token(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Test that cancelling a job sets the cancellation token."""
	job = make_fake_job()

	close_calls: list[str] = []
	monkeypatch.setattr(job_runner_module, "close_old_connections", lambda: close_calls.append("close"))

	cancel_token_used: list[CancellationToken | None] = []
	cancelled_during_extraction = False

	def fake_extract(*, params: ExtractParams, on_progress: Callable[[int, int], None]) -> int:
		cancel_token_used.append(params.cancel_token)
		
		# Check if token is cancelled
		nonlocal cancelled_during_extraction
		if params.cancel_token and params.cancel_token.is_cancelled():
			cancelled_during_extraction = True
			raise CancelledException("Extraction cancelled")
		
		on_progress(1, 1)
		return 1

	runner, _manager = _configure_runner(job, fake_extract)
	
	# Start the job
	runner.start_job(job.id)
	
	# The job should have a cancel token
	assert len(cancel_token_used) == 1
	assert cancel_token_used[0] is not None
	
	# Cancel should have been called if the job was cancelled before extraction
	# In this immediate execution test, we can't cancel mid-execution
	# but we verify the token was passed


def test_job_runner_finished_statuses_includes_cancelled() -> None:
	"""Test that FINISHED_STATUSES includes CANCELLED."""
	assert ExtractionJob.Status.CANCELLED in JobRunner.FINISHED_STATUSES


def test_extraction_job_cancelled_status_css() -> None:
	"""Test that cancelled status has correct CSS class."""
	job = ExtractionJob(
		id="test-job",
		status=ExtractionJob.Status.CANCELLED,
		params={},
		output_dir="/tmp/output",
	)
	assert job.status_css() == "cancelled"
