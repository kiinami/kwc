from pathlib import Path
import logging
from tempfile import NamedTemporaryFile, TemporaryDirectory

import cv2
import json
from ffmpeg import FFmpeg, Progress as FFmpegProgress
from rich.progress import Progress, TimeElapsedColumn, MofNCompleteColumn

logger = logging.getLogger(__name__)


def total_frames(video: Path) -> int:
    cap = cv2.VideoCapture(str(video))
    return int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

def total_keyframes(video: Path) -> int:
    ffprobe = FFmpeg(executable="ffprobe").input(
        video,
        select_streams="v:0",
        skip_frame="nokey",
        show_entries="frame=pict_type",
        print_format="json",
        show_frames=None,
    )
    
    with Progress(*Progress.get_default_columns(), TimeElapsedColumn(), transient=True) as progress:
        progress.add_task(f'Getting keyframe count for "{video}"', total=None)

        output = ffprobe.execute()
        
    data = json.loads(output)
    
    i_frames = [f for f in data.get("frames", []) if f.get("pict_type") == "I"]
    return len(i_frames)


def trim_video(video: Path, output: Path, start: str = None, end: str = None):
    if start and end:
        options = {"ss": start, "to": end}
    elif start:
        options = {"ss": start}
    elif end:
        options = {"to": end}
    else:
        options = {}
    options.update({'c:v': 'copy'})
    ffmpeg = (
        FFmpeg()
        .option('y')
        .input(str(video))
        .output(
            str(output),
            options,
            an=None,
        )
    )
    ffmpeg.execute()
    logger.info(f'Trimmed "{video.absolute()}" to "{output.absolute()}"')


def transcode_video(video: Path, width: int, height: int):
    total = total_frames(video)
    with NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
        ffmpeg = (
            FFmpeg()
            .option('y')
            .input(str(video))
            .output(
                tmp.name,
                vcodec="libx264",
                vf=f'scale={width}:{height}',
                an=None,
                vsync='passthrough',
            )
        )

        with Progress(*Progress.get_default_columns(), TimeElapsedColumn(), MofNCompleteColumn(),
                      transient=True) as progress:
            task = progress.add_task(f'Transcoding "{video}" to {height}p', total=total)

            @ffmpeg.on('progress')
            def on_progress(ffmpeg_progress: FFmpegProgress):
                progress.update(task, completed=ffmpeg_progress.frame)

            ffmpeg.execute()

    return Path(tmp.name)


def cut_video(video: Path, intervals: list[tuple[str, ...]]):
    with NamedTemporaryFile(suffix='.mp4', delete=False) as output:
        output = Path(output.name)
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            for i, (start, end) in enumerate(intervals):
                output_file = tmpdir / f'output_{i:03d}.mp4'
                trim_video(video, output_file, start, end)

            ffmpeg = (
                FFmpeg()
                .option('y')
                .input(str(tmpdir / 'output_%03d.mp4'), pattern_type='glob')
                .output(str(output), c='copy', f='concat')
            )
            ffmpeg.execute()
            logger.info(f'Cut video saved to "{output.absolute()}"')

        return output


def get_iframe_timestamps(video: Path) -> list[float]:
    """
    Return a list of timestamps (in seconds) for all I-frames in the video.
    """
    ffprobe = FFmpeg(executable="ffprobe").input(
        video,
        select_streams="v:0",
        skip_frame="nokey",
        show_entries="frame=pict_type,best_effort_timestamp_time",
        print_format="json",
        show_frames=None,
    )
    with Progress(*Progress.get_default_columns(), TimeElapsedColumn(), transient=True) as progress:
        progress.add_task(f'Getting keyframe timestamps for "{video}"', total=None)
        output = ffprobe.execute()
    data = json.loads(output)
    timestamps = [float(f["best_effort_timestamp_time"]) for f in data.get("frames", []) if f.get("pict_type") == "I" and f.get("best_effort_timestamp_time") is not None]
    return timestamps
