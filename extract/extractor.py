from __future__ import annotations

import concurrent.futures
import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from ffmpeg import FFmpeg

from .utils import check_is_hdr, cut_video, get_iframe_timestamps, render_pattern

logger = logging.getLogger(__name__)
_sleep = time.sleep


class CancellationToken:
	"""Thread-safe token for signaling cancellation."""
	
	def __init__(self) -> None:
		self._cancelled = False
		self._lock = threading.Lock()
	
	def cancel(self) -> None:
		with self._lock:
			self._cancelled = True
	
	def is_cancelled(self) -> bool:
		with self._lock:
			return self._cancelled


class CancelledException(Exception):
	"""Raised when an extraction is cancelled."""
	pass


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
    retries = max(retries, 0)
    if backoff < 0:
        backoff = 0.0
    return retries, backoff


def _find_highest_counter(output_dir: Path, pattern: str, context: Mapping[str, str | int]) -> int:
    """
    Find the highest counter value in existing files that match the pattern.
    Returns 0 if no matching files are found or if the directory doesn't exist.
    """
    if not output_dir.exists():
        return 0
    
    # We need to determine which files match our pattern by rendering it with different counters
    # and comparing. Since we don't know the range, we'll iterate through existing files and try
    # to extract the counter by comparing against the pattern.
    
    highest = 0
    
    try:
        for entry in output_dir.iterdir():
            if not entry.is_file():
                continue
            
            filename = entry.name
            
            # Try to extract counter by testing various counter values
            # We'll render the pattern with different counters and see which one matches the filename
            # Since filenames use zero-padding, we need to handle that
            
            # First, determine if the filename could match by rendering with a dummy counter
            # and checking if the non-counter parts match
            
            # Strategy: Generate pattern with counter=999999 (unlikely to collide)
            # Replace that number with a regex and match
            test_counter = 999999
            try:
                test_rendered = render_pattern(
                    pattern,
                    {**context, "counter": test_counter}
                )
            except Exception:
                continue
            
            # Find where the counter appears in the rendered pattern
            counter_str = str(test_counter)
            if counter_str not in test_rendered:
                # Pattern doesn't include counter, skip
                continue
            
            # Split the rendered pattern into parts before and after the counter
            parts = test_rendered.split(counter_str, 1)
            if len(parts) != 2:
                continue
            
            prefix, suffix = parts
            
            # Check if the filename matches the pattern structure
            if not filename.startswith(prefix) or not filename.endswith(suffix):
                continue
            
            # Extract the counter part from the filename
            counter_part = filename[len(prefix):-len(suffix)] if suffix else filename[len(prefix):]
            
            # Try to parse it as an integer
            try:
                counter = int(counter_part)
                highest = max(highest, counter)
            except ValueError:
                continue
                
    except OSError as e:
        logger.warning("Error reading directory %s: %s", output_dir, e)
    
    return highest


def _extract_frame(args: tuple[Path, float, Path, bool]) -> Path:
    video, ts, output_file, is_hdr = args
    retries, backoff = _get_retry_config()
    attempt = 0
    while True:
        try:
            ffmpeg = FFmpeg().option("y").input(str(video), ss=ts)
            if is_hdr:
                # HDR to SDR tone mapping using zscale and hable
                # Note: This requires ffmpeg with libzimg support, which is standard in many builds including Debian's
                vf = (
                    "zscale=t=linear:npl=100,"
                    "format=gbrpf32le,"
                    "zscale=p=bt709,"
                    "tonemap=tonemap=hable:desat=0,"
                    "zscale=t=bt709:m=bt709:r=tv,"
                    "format=yuv420p"
                )
                ffmpeg = ffmpeg.output(str(output_file), frames="1", q="2", vf=vf)
            else:
                ffmpeg = ffmpeg.output(str(output_file), frames="1", q="2")
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
    cancel_token: CancellationToken | None = None


def extract(
    *,
    params: ExtractParams,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """
    Extract frames for each I-frame in a video. Returns number of frames extracted.

    on_progress(current, total) can be used to track progress.
    """
    # Check for cancellation early
    if params.cancel_token and params.cancel_token.is_cancelled():
        raise CancelledException("Extraction cancelled")
    
    video = params.video
    output_dir = params.output_dir
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    if params.trim_intervals:
        video = cut_video(video, [tuple(interval.split("-")) for interval in params.trim_intervals])

    logger.info('Extracting frames from "%s" to "%s"...', video.absolute(), output_dir.absolute())

    # Check for cancellation before getting timestamps
    if params.cancel_token and params.cancel_token.is_cancelled():
        raise CancelledException("Extraction cancelled")

    # Check for HDR content
    is_hdr = check_is_hdr(video)
    if is_hdr:
        logger.info("HDR video detected: enabling tone mapping for %s", video.name)

    timestamps = get_iframe_timestamps(video)
    logger.debug("Found %d keyframes", len(timestamps))

    # Build filename pattern
    pattern = params.image_pattern or "output {{ counter|pad:4 }}.jpg"
    
    # Find highest existing counter to append new files
    context_for_pattern = {
        "title": params.title,
        "year": params.year or "",
        "season": params.season or "",
        "episode": params.episode or "",
    }
    start_counter = _find_highest_counter(output_dir, pattern, context_for_pattern) + 1
    logger.debug("Starting counter at %d (appending to existing files)", start_counter)
    
    frame_args: list[tuple[Path, float, Path, bool]] = []
    for idx, ts in enumerate(timestamps, start_counter):
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
        frame_args.append((video, ts, output_dir / name, is_hdr))

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
                # Check for cancellation
                if params.cancel_token and params.cancel_token.is_cancelled():
                    # Cancel all pending futures
                    for future in futures:
                        future.cancel()
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise CancelledException("Extraction cancelled")
                
                # Retrieve result to surface exceptions immediately
                f.result()
                done += 1
                if on_progress:
                    on_progress(done, total)

    logger.info('Extracted %d frames from "%s" to "%s"!', done, video, output_dir)
    return done
