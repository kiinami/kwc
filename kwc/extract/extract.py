import logging
from pathlib import Path

from ffmpeg import FFmpeg
from rich.progress import Progress, TimeElapsedColumn

from .utils import transcode_video, cut_video

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
    ffmpeg = (
        FFmpeg()
        .option('y')
        .input(str(video))
        .output(
            f"{str(output_dir)}/output_%04d.jpg",
            vf='select=eq(pict_type\\,I)',
            vsync='vfr'
        )
    )
    with Progress(*Progress.get_default_columns(), TimeElapsedColumn(), transient=True) as progress:
        progress.add_task(f'Extracting frames from "{video}"', total=None)

        ffmpeg.execute()

    logger.info(f'Extracted {len(output_dir.glob("*.jpg"))} frames from "{video}" to "{output_dir}"!')
