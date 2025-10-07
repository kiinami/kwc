from __future__ import annotations

import concurrent.futures
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from ffmpeg import FFmpeg

from .utils import cut_video, get_iframe_timestamps, render_pattern

logger = logging.getLogger(__name__)


def _extract_frame(args: tuple[Path, float, Path]) -> Path:
    video, ts, output_file = args
    try:
        ffmpeg = FFmpeg().option("y").input(str(video), ss=ts).output(str(output_file), frames="1", q="2")
        ffmpeg.execute()
        return output_file
    except Exception as e:  # propagate so parent marks job as error
        logger.exception("ffmpeg failed extracting frame at %s from %s -> %s", ts, video, output_file)
        raise


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
    pattern = params.image_pattern or "output_{counter:04}.jpg"
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
        with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = {executor.submit(_extract_frame, arg): arg for arg in frame_args}
            for f in concurrent.futures.as_completed(futures):
                # Retrieve result to surface exceptions immediately
                f.result()
                done += 1
                if on_progress:
                    on_progress(done, total)

    logger.info('Extracted %d frames from "%s" to "%s"!', done, video, output_dir)
    return done
