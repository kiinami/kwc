from __future__ import annotations

import json
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from django.template import Context, Engine
from ffmpeg import FFmpeg

logger = logging.getLogger(__name__)


PATTERN_ENGINE = Engine(builtins=["extract.templatetags.naming"])


def trim_video(video: Path, output: Path, start: str | None = None, end: str | None = None) -> None:
    if start and end:
        options = {"ss": start, "to": end}
    elif start:
        options = {"ss": start}
    elif end:
        options = {"to": end}
    else:
        options = {}
    options.update({"c:v": "copy"})
    ffmpeg = (
        FFmpeg()
        .option("y")
        .input(str(video))
        .output(
            str(output),
            options,
            an=None,
        )
    )
    try:
        ffmpeg.execute()
    except Exception:
        logger.exception("ffmpeg trim failed: %s -> %s", video, output)
        raise
    logger.info('Trimmed "%s" to "%s"', video.absolute(), output.absolute())


def cut_video(video: Path, intervals: list[tuple[str, ...]]) -> Path:
    with NamedTemporaryFile(suffix=".mp4", delete=False) as output:
        output_path = Path(output.name)
        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            for i, (start, end) in enumerate(intervals):
                part_out = tmpdir_path / f"output_{i:03d}.mp4"
                trim_video(video, part_out, start, end)

            ffmpeg = (
                FFmpeg()
                .option("y")
                .input(str(tmpdir_path / "output_%03d.mp4"), pattern_type="glob")
                .output(str(output_path), c="copy", f="concat")
            )
            try:
                ffmpeg.execute()
            except Exception:
                logger.exception("ffmpeg concat failed in cut_video for %s", video)
                raise
            logger.info('Cut video saved to "%s"', output_path.absolute())

        return output_path


def get_iframe_timestamps(video: Path) -> list[float]:
    """
    Return a list of timestamps (in seconds) for all I-frames in the video.
    """
    ffprobe = FFmpeg(executable="ffprobe").input(
        str(video),
        select_streams="v:0",
        skip_frame="nokey",
        show_entries="frame=pict_type,best_effort_timestamp_time",
        print_format="json",
        show_frames=None,
    )
    try:
        output = ffprobe.execute()
    except Exception as exc:
        logger.exception("ffprobe failed listing iframe timestamps for %s: %s", video, exc)
        return []
    data = json.loads(output)
    timestamps = [
        float(f["best_effort_timestamp_time"])
        for f in data.get("frames", [])
        if f.get("pict_type") == "I" and f.get("best_effort_timestamp_time") is not None
    ]
    return timestamps


def render_pattern(pattern: str, values: dict[str, object]) -> str:
    """Render a naming pattern using Django template engine.

    The pattern can use template variables like {{ title }}, {{ counter }}, {{ year }}, {{ season }}, {{ episode }}
    and the custom filter "pad" from extract.templatetags.naming, for example: {{ counter|pad:4 }}.
    """
    tpl = PATTERN_ENGINE.from_string(pattern)
    return tpl.render(Context(values))  # type: ignore[no-any-return]


def check_is_hdr(video: Path) -> bool:
    """
    Check if the video has HDR metadata (transfer characteristics).
    """
    ffprobe = FFmpeg(executable="ffprobe").input(
        str(video),
        select_streams="v:0",
        show_entries="stream=color_transfer",
        print_format="json",
    )
    try:
        output = ffprobe.execute()
        data = json.loads(output)
        streams = data.get("streams", [])
        if not streams:
            return False

        stream = streams[0]
        # Common HDR transfer characteristics
        # smpte2084 is PQ (perceptual quantizer) -> HDR10 / Dolby Vision
        # arib-std-b67 is HLG (hybrid log-gamma)
        hdr_transfers = {"smpte2084", "arib-std-b67"}

        transfer = stream.get("color_transfer")

        return transfer in hdr_transfers
    except Exception as exc:
        logger.warning("ffprobe failed extracting video metadata for %s: %s", video, exc)
        return False
