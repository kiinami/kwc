from __future__ import annotations

import concurrent.futures
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from django.conf import settings
from ffmpeg import FFmpeg

from .utils import cut_video, get_iframe_timestamps, render_pattern

logger = logging.getLogger(__name__)
_sleep = time.sleep


def _get_retry_config() -> tuple[int, float]:
    retries = getattr(settings, "EXTRACT_FFMPEG_RETRIES", 2)
    backoff = getattr(settings, "EXTRACT_FFMPEG_RETRY_BACKOFF", 0.5)
    try:
        retries = int(retries)
    except (TypeError, ValueError):
        retries = 2
    try:
        backoff = float(backoff)
    except (TypeError, ValueError):
        backoff = 0.5
    if retries < 0:
        retries = 0
    if backoff < 0:
        backoff = 0.0
    return retries, backoff


def _extract_frame(args: tuple[Path, float, Path]) -> Path:
    video, ts, output_file = args
    retries, backoff = _get_retry_config()
    attempt = 0
    while True:
        try:
            ffmpeg = FFmpeg().option("y").input(str(video), ss=ts).output(str(output_file), frames="1", q="2")
            ffmpeg.execute()
            return output_file
        except Exception as exc:  # propagate so parent marks job as error
            if attempt >= retries:
                logger.exception(
                    "ffmpeg failed extracting frame at %s from %s -> %s after %d attempts",
                    ts,
                    video,
                    output_file,
                    attempt + 1,
                )
                raise
            attempt += 1
            logger.warning(
                "ffmpeg extract retry %d/%d for %s (%s)",
                attempt,
                retries,
                video,
                exc,
            )
            delay = backoff * attempt
            if delay > 0:
                _sleep(delay)


@dataclass
class ExtractParams:
    video: Path
    output_dir: Path
    trim_intervals: list[str] | None = None
    title: str = ""
    image_pattern: str | None = None
    year: int | None = None
    season: int | None = None
    episode: str | int | None = None
    max_workers: int | None = None


def extract(
    *,
    params: ExtractParams,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """
    Extract frames for each I-frame in a video. Returns number of frames extracted.

    on_progress(current, total) can be used to track progress.
    """
    video = params.video
    output_dir = params.output_dir
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    if params.trim_intervals:
        video = cut_video(video, [tuple(interval.split("-")) for interval in params.trim_intervals])

    logger.info('Extracting frames from "%s" to "%s"...', video.absolute(), output_dir.absolute())

    timestamps = get_iframe_timestamps(video)
    logger.debug("Found %d keyframes", len(timestamps))

    # Build filename pattern
    pattern = params.image_pattern or "output {{ counter|pad:4 }}.jpg"
    frame_args: list[tuple[Path, float, Path]] = []
    for idx, ts in enumerate(timestamps, 1):
        try:
            name = render_pattern(
                pattern,
                {
                    "title": params.title,
                    "counter": idx,
                    "year": params.year or "",
                    "season": params.season or "",
                    "episode": params.episode or "",
                },
            )
        except Exception:
            # Fallback in case of unexpected error
            name = f"output_{idx:04d}.jpg"
        frame_args.append((video, ts, output_dir / name))

    total = len(frame_args)
    done = 0
    if on_progress:
        on_progress(done, total)

    # Use processes to parallelize decoding
    if total:
        max_workers = params.max_workers
        if max_workers is not None:
            try:
                max_workers = int(max_workers)
            except (TypeError, ValueError):
                max_workers = None
            else:
                if max_workers <= 0:
                    max_workers = None
        if max_workers is None:
            max_workers = getattr(settings, "EXTRACT_MAX_WORKERS", None)
            if max_workers is not None:
                try:
                    max_workers = int(max_workers)
                except (TypeError, ValueError):
                    max_workers = None
                else:
                    if max_workers <= 0:
                        max_workers = None
        if max_workers is None:
            max_workers = os.cpu_count() or 1
            logger.debug("Using default max workers: %d", max_workers)
        else:
            logger.debug("Using configured max workers: %d", max_workers)
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_extract_frame, arg): arg for arg in frame_args}
            for f in concurrent.futures.as_completed(futures):
                # Retrieve result to surface exceptions immediately
                f.result()
                done += 1
                if on_progress:
                    on_progress(done, total)

    logger.info('Extracted %d frames from "%s" to "%s"!', done, video, output_dir)
    return done
