from __future__ import annotations

from pathlib import Path

import pytest

from extract import extractor
from extract import utils as extract_utils


class StubFFmpeg:
	def __init__(self, execute_behaviour):
		self._execute_behaviour = execute_behaviour

	def option(self, *_args, **_kwargs):
		return self

	def input(self, *_args, **_kwargs):
		return self

	def output(self, *_args, **_kwargs):
		return self

	def execute(self):
		self._execute_behaviour()


# Module-level mock function that can be pickled for multiprocessing
def _mock_extract_frame_with_file_creation(args: tuple[Path, float, Path]) -> Path:
	_video, _ts, output_file = args
	output_file.touch()  # Create the file
	return output_file


def test_extract_frame_retries_success(monkeypatch: pytest.MonkeyPatch, settings) -> None:
	attempts: list[str] = []

	def behaviour() -> None:
		if not attempts:
			attempts.append("fail")
			raise RuntimeError("boom")
		attempts.append("success")

	settings.EXTRACT_FFMPEG_RETRIES = 2
	settings.EXTRACT_FFMPEG_RETRY_BACKOFF = 0.0
	monkeypatch.setattr(extractor, "FFmpeg", lambda *args, **kwargs: StubFFmpeg(behaviour))
	monkeypatch.setattr(extractor, "_sleep", lambda _delay: None)

	result = extractor._extract_frame((Path("/tmp/video.mp4"), 0.0, Path("/tmp/frame.jpg")))
	assert result == Path("/tmp/frame.jpg")
	assert attempts == ["fail", "success"]


def test_extract_frame_retries_exhaust(monkeypatch: pytest.MonkeyPatch, settings) -> None:
	attempts = 0

	def behaviour() -> None:
		nonlocal attempts
		attempts += 1
		raise RuntimeError("still failing")

	settings.EXTRACT_FFMPEG_RETRIES = 1
	settings.EXTRACT_FFMPEG_RETRY_BACKOFF = 0.0
	monkeypatch.setattr(extractor, "FFmpeg", lambda *args, **kwargs: StubFFmpeg(behaviour))
	monkeypatch.setattr(extractor, "_sleep", lambda _delay: None)

	with pytest.raises(RuntimeError):
		extractor._extract_frame((Path("/tmp/video.mp4"), 0.0, Path("/tmp/frame.jpg")))
	assert attempts == 2


def test_get_iframe_timestamps_logs_failure(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
	def failing_execute() -> None:
		raise RuntimeError("ffprobe crashed")

	monkeypatch.setattr(extract_utils, "FFmpeg", lambda *args, **kwargs: StubFFmpeg(failing_execute))
	caplog.set_level("ERROR", logger="extract.utils")

	result = extract_utils.get_iframe_timestamps(Path("/tmp/nonexistent.mp4"))
	assert result == []
	assert "ffprobe failed" in caplog.text
	assert "nonexistent.mp4" in caplog.text


def test_find_highest_counter_empty_directory(tmp_path: Path) -> None:
	"""Test that an empty directory returns 0."""
	pattern = "{{ title }} ~ {{ counter|pad:4 }}.jpg"
	context = {"title": "Test"}
	result = extractor._find_highest_counter(tmp_path, pattern, context)
	assert result == 0


def test_find_highest_counter_nonexistent_directory(tmp_path: Path) -> None:
	"""Test that a nonexistent directory returns 0."""
	nonexistent = tmp_path / "nonexistent"
	pattern = "{{ title }} ~ {{ counter|pad:4 }}.jpg"
	context = {"title": "Test"}
	result = extractor._find_highest_counter(nonexistent, pattern, context)
	assert result == 0


def test_find_highest_counter_with_matching_files(tmp_path: Path) -> None:
	"""Test finding highest counter with matching files."""
	# Create files with counters
	(tmp_path / "Test ~ 0001.jpg").touch()
	(tmp_path / "Test ~ 0005.jpg").touch()
	(tmp_path / "Test ~ 0010.jpg").touch()
	
	pattern = "{{ title }} ~ {{ counter|pad:4 }}.jpg"
	context = {"title": "Test"}
	result = extractor._find_highest_counter(tmp_path, pattern, context)
	assert result == 10


def test_find_highest_counter_with_non_matching_files(tmp_path: Path) -> None:
	"""Test that non-matching files are ignored."""
	(tmp_path / "Test ~ 0001.jpg").touch()
	(tmp_path / "Other ~ 0050.jpg").touch()  # Different title
	(tmp_path / "random.txt").touch()  # Different pattern
	
	pattern = "{{ title }} ~ {{ counter|pad:4 }}.jpg"
	context = {"title": "Test"}
	result = extractor._find_highest_counter(tmp_path, pattern, context)
	assert result == 1


def test_find_highest_counter_with_year(tmp_path: Path) -> None:
	"""Test pattern with year in title."""
	(tmp_path / "Test Title (2025) ~ 0001.jpg").touch()
	(tmp_path / "Test Title (2025) ~ 0015.jpg").touch()
	
	pattern = "{{ title }}{% if year %} ({{ year }}){% endif %} ~ {{ counter|pad:4 }}.jpg"
	context = {"title": "Test Title", "year": "2025"}
	result = extractor._find_highest_counter(tmp_path, pattern, context)
	assert result == 15


def test_find_highest_counter_with_season_episode(tmp_path: Path) -> None:
	"""Test pattern with season and episode."""
	(tmp_path / "Test S01E01 ~ 0001.jpg").touch()
	(tmp_path / "Test S01E01 ~ 0020.jpg").touch()
	
	pattern = "{{ title }}{% if season %} S{{ season|pad:2 }}{% endif %}{% if episode %}E{{ episode|pad:2 }}{% endif %} ~ {{ counter|pad:4 }}.jpg"
	context = {"title": "Test", "season": "01", "episode": "01"}
	result = extractor._find_highest_counter(tmp_path, pattern, context)
	assert result == 20


def test_find_highest_counter_without_pad(tmp_path: Path) -> None:
	"""Test pattern without padding on counter."""
	(tmp_path / "output_1.jpg").touch()
	(tmp_path / "output_25.jpg").touch()
	
	pattern = "output_{{ counter }}.jpg"
	context = {}
	result = extractor._find_highest_counter(tmp_path, pattern, context)
	assert result == 25


def test_find_highest_counter_pattern_without_counter(tmp_path: Path) -> None:
	"""Test that pattern without counter returns 0."""
	(tmp_path / "test.jpg").touch()
	
	pattern = "{{ title }}.jpg"
	context = {"title": "test"}
	result = extractor._find_highest_counter(tmp_path, pattern, context)
	assert result == 0


def test_extract_appends_to_existing_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings) -> None:
	"""Test that extract starts counter from highest existing file + 1."""
	output_dir = tmp_path / "output"
	output_dir.mkdir()
	
	# Create existing files
	(output_dir / "Test ~ 0001.jpg").touch()
	(output_dir / "Test ~ 0005.jpg").touch()
	
	# Use module-level mock function that can be pickled
	monkeypatch.setattr(extractor, "_extract_frame", _mock_extract_frame_with_file_creation)
	monkeypatch.setattr(extractor, "get_iframe_timestamps", lambda _video: [1.0, 2.0, 3.0])
	
	params = extractor.ExtractParams(
		video=Path("/tmp/test.mp4"),
		output_dir=output_dir,
		title="Test",
		image_pattern="{{ title }} ~ {{ counter|pad:4 }}.jpg",
		max_workers=1,  # Use single worker to avoid multiprocessing issues with mocked functions
	)
	
	result = extractor.extract(params=params)
	
	# Check that 3 frames were extracted
	assert result == 3
	
	# Check that new files start from 6 (highest was 5)
	assert (output_dir / "Test ~ 0006.jpg").exists()
	assert (output_dir / "Test ~ 0007.jpg").exists()
	assert (output_dir / "Test ~ 0008.jpg").exists()
	# Old files should still exist
	assert (output_dir / "Test ~ 0001.jpg").exists()
	assert (output_dir / "Test ~ 0005.jpg").exists()