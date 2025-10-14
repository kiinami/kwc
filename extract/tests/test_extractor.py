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