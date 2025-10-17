from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from extract import job_runner as job_runner_module
from extract.extractor import ExtractParams
from extract.job_runner import JobRunner
from extract.models import ExtractionJob


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
				self._job.status_transitions.append(self._job.status)
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
			self.status_transitions.append(self.status)
		self.updated_at = timezone.now()

	def refresh_from_db(self) -> None:
		self.refreshed += 1


def _configure_runner(job: FakeJob, extractor: Callable[..., int]) -> tuple[JobRunner, FakeManager]:
	FakeModel.objects = FakeManager(job)
	manager = FakeModel.objects
	runner = JobRunner(model=FakeModel, extractor=extractor)

	def thread_factory(target: Callable[[str], None], args: tuple[str, ...]) -> ImmediateThread:
		return ImmediateThread(runner, target, args)

	runner._thread_factory = thread_factory
	return runner, manager


def test_job_runner_marks_job_done(monkeypatch: pytest.MonkeyPatch) -> None:
	job = make_fake_job()

	close_calls: list[str] = []
	monkeypatch.setattr(job_runner_module, "close_old_connections", lambda: close_calls.append("close"))

	progress: list[tuple[int, int]] = []

	def fake_extract(*, params: ExtractParams, on_progress: Callable[[int, int], None]) -> int:
		assert isinstance(params, ExtractParams)
		on_progress(1, 3)
		on_progress(3, 3)
		progress.append((1, 3))
		progress.append((3, 3))
		return 3

	runner, manager = _configure_runner(job, fake_extract)
	runner.start_job(job.id)

	assert job.status == ExtractionJob.Status.DONE
	assert job.finished_at is not None
	assert job.started_at is not None
	assert job.total_frames == 3
	assert job.current_step == job.total_steps == 3
	assert job.error == ""
	assert progress == [(1, 3), (3, 3)]
	assert job.status_transitions == [ExtractionJob.Status.RUNNING, ExtractionJob.Status.DONE]
	assert not runner.is_running(job.id)
	assert len(manager.update_calls) >= 2
	assert len(close_calls) >= 2


def test_job_runner_records_error(monkeypatch: pytest.MonkeyPatch) -> None:
	job = make_fake_job()

	close_calls: list[str] = []
	monkeypatch.setattr(job_runner_module, "close_old_connections", lambda: close_calls.append("close"))

	class Boom(Exception):
		pass

	def boom_extract(**_: Any) -> int:
		raise Boom("explode")

	runner, manager = _configure_runner(job, boom_extract)
	runner.start_job(job.id)

	assert job.status == ExtractionJob.Status.ERROR
	assert job.error == "explode"
	assert job.finished_at is not None
	assert not runner.is_running(job.id)
	assert job.status_transitions[0] == ExtractionJob.Status.RUNNING
	assert len(manager.update_calls) >= 1
	assert len(close_calls) >= 2