import logging
from pathlib import Path

from ffmpeg import FFmpeg
from rich.progress import Progress, TimeElapsedColumn


logger = logging.getLogger(__name__)


def extract_ffmpeg(
        video: Path,
        output_dir: Path = Path('out'),
):
    """
    Extract frames from a video file.

    Args:
        video (Path): Path to the video file.
        output_dir (Path): Directory where extracted frames will be saved.

    """
    if not video.exists():
        raise FileNotFoundError(f"Video file '{video}' does not exist.")

    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

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

    logger.info(f'Extracted {len(output_dirt)} frames from "{video}" to "{output_dir}"!')
