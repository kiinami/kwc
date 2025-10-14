from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable

from django.test import SimpleTestCase, override_settings
from unittest.mock import patch

from .extractor import ExtractParams, extract


class ExtractorWorkerSelectionTests(SimpleTestCase):
	def _run_extract_with_patched_executor(
		self,
		*,
		override: int | None,
		cpu_count_value: int,
		expected_workers: int,
		params_override: int | None = None,
	) -> None:
		class FakeFuture:
			def result(self) -> None:
				return None

		class FakeExecutor:
			def __init__(self, *, max_workers: int | None = None):
				self.max_workers = max_workers

			def __enter__(self) -> "FakeExecutor":
				return self

			def __exit__(self, exc_type, exc, tb) -> None:
				return None

			def submit(self, fn, arg):
				return FakeFuture()

		created_executors: list[FakeExecutor] = []

		def executor_factory(*args, **kwargs):
			executor = FakeExecutor(max_workers=kwargs.get("max_workers"))
			created_executors.append(executor)
			return executor

		def as_completed(iterable: Iterable):
			for item in iterable:
				yield item

		with TemporaryDirectory() as tmpdir:
			temp_path = Path(tmpdir)
			video = temp_path / "input.mp4"
			video.touch()
			output = temp_path / "output"
			output.mkdir()

			params = ExtractParams(video=video, output_dir=output, max_workers=params_override)
			with override_settings(EXTRACT_MAX_WORKERS=override):
				with patch("extract.extractor.get_iframe_timestamps", return_value=[0.0]):
					with patch("extract.extractor.render_pattern", side_effect=lambda pattern, values: "frame.jpg"):
						with patch("extract.extractor.concurrent.futures.ProcessPoolExecutor", side_effect=executor_factory):
							with patch("extract.extractor.concurrent.futures.as_completed", side_effect=as_completed):
								with patch("extract.extractor.os.cpu_count", return_value=cpu_count_value):
									extract(params=params)

		self.assertEqual(len(created_executors), 1)
		self.assertEqual(created_executors[0].max_workers, expected_workers)

	def test_uses_cpu_count_when_setting_missing(self) -> None:
		self._run_extract_with_patched_executor(override=None, cpu_count_value=4, expected_workers=4)

	def test_uses_override_when_present(self) -> None:
		self._run_extract_with_patched_executor(override=2, cpu_count_value=6, expected_workers=2)

	def test_params_max_workers_override(self) -> None:
		self._run_extract_with_patched_executor(
			override=5,
			cpu_count_value=6,
			expected_workers=3,
			params_override=3,
		)
