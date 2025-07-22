import logging
from pathlib import Path
import subprocess

import json

from ffmpeg import FFmpeg, Progress as FFmpegProgress
from rich.progress import Progress, TimeElapsedColumn, MofNCompleteColumn

from .utils import transcode_video, cut_video, get_iframe_timestamps

logger = logging.getLogger(__name__)


def extract(
        video: Path,
        output_dir: Path,
        transcode: bool = False,
        transcode_width: int = 1920,
        transcode_height: int = 1080,
        trim_intervals: list[str] = None,
):
    """
    Extract frames from a video file.

    Args:
        video (Path): Path to the video file.
        output_dir (Path): Directory where extracted frames will be saved.
        transcode (bool): Whether to transcode the video to a specific resolution before extracting frames.
        transcode_width (int): Width of the transcoded video.
        transcode_height (int): Height of the transcoded video.
        trim_intervals (list[str]): List of intervals to trim the video, formatted as "start-end" (e.g., "00:00:10-00:00:20").

    """
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    if transcode:
        video = transcode_video(video, transcode_width, transcode_height)

    if trim_intervals:
        video = cut_video(video, [tuple(interval.split('-')) for interval in trim_intervals])


    logger.info(f'Extracting frames from "{video.absolute()}" to "{output_dir.absolute()}"...')

    # Get I-frame timestamps
    timestamps = get_iframe_timestamps(video)
    logger.info(f'Found {len(timestamps)} I-frames.')

    with Progress(*Progress.get_default_columns(), TimeElapsedColumn(), MofNCompleteColumn(),
                      transient=True) as progress:
        task = progress.add_task(f'Extracting frames from "{video}"', total=len(timestamps))

        for idx, ts in enumerate(timestamps, 1):
            output_file = output_dir / f"output_{idx:04d}.jpg"
            ffmpeg = (
                FFmpeg()
                .option('y')
                .input(str(video), ss=ts)
                .output(str(output_file), frames='1', q='2')
            )
            ffmpeg.execute()
            progress.update(task, completed=idx)

    logger.info(f'Extracted {len(list(output_dir.glob("*.jpg")))} frames from "{video}" to "{output_dir}"!')
