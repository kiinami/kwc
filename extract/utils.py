from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from tempfile import NamedTemporaryFile, TemporaryDirectory

from ffmpeg import FFmpeg, Progress as FFmpegProgress
from django.template import Engine, Context

logger = logging.getLogger(__name__)


def total_frames(video: Path) -> int:
    """Best-effort total frame count using ffprobe metadata.

    Note: Some containers don't report nb_frames; we fallback to duration * avg_frame_rate.
    """
    ffprobe = (
        FFmpeg(executable="ffprobe")
        .input(
            str(video),
            show_entries="stream=nb_frames,avg_frame_rate,duration",
            select_streams="v:0",
            print_format="json",
            show_streams=None,
        )
    )
    try:
        out = ffprobe.execute()
    except Exception:
        logger.exception("ffprobe failed reading total_frames for %s", video)
        return 0
    data = json.loads(out)
    streams = data.get("streams", [])
    if not streams:
        return 0
    s = streams[0]
    try:
        nb = int(s.get("nb_frames") or 0)
    except (TypeError, ValueError):
        nb = 0
    if nb > 0:
        return nb
    # Fallback
    dur = float(s.get("duration") or 0.0)
    afr = s.get("avg_frame_rate") or "0/1"
    try:
        num, den = afr.split("/")
        fps = float(num) / (float(den) or 1.0)
    except Exception:
        fps = 0.0
    return int(dur * fps) if dur > 0 and fps > 0 else 0


def total_keyframes(video: Path) -> int:
    ffprobe = (
        FFmpeg(executable="ffprobe")
        .input(
            str(video),
            select_streams="v:0",
            skip_frame="nokey",
            show_entries="frame=pict_type",
            print_format="json",
            show_frames=None,
        )
    )

    try:
        output = ffprobe.execute()
    except Exception:
        logger.exception("ffprobe failed reading keyframes for %s", video)
        return 0
    data = json.loads(output)
    i_frames = [f for f in data.get("frames", []) if f.get("pict_type") == "I"]
    return len(i_frames)


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


# Transcode functionality removed


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
    ffprobe = (
        FFmpeg(executable="ffprobe")
        .input(
            str(video),
            select_streams="v:0",
            skip_frame="nokey",
            show_entries="frame=pict_type,best_effort_timestamp_time",
            print_format="json",
            show_frames=None,
        )
    )
    try:
        output = ffprobe.execute()
    except Exception:
        logger.exception("ffprobe failed listing iframe timestamps for %s", video)
        return []
    data = json.loads(output)
    timestamps = [
        float(f["best_effort_timestamp_time"])
        for f in data.get("frames", [])
        if f.get("pict_type") == "I" and f.get("best_effort_timestamp_time") is not None
    ]
    return timestamps


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::(\d+))?\}")

# Optional leading-space handling for season/episode placeholders
_OPT_SPACE_SEASON_EP = re.compile(r"( )?\{(season|episode)(?::(\d+))?\}")


def render_pattern(pattern: str, values: dict[str, object]) -> str:
    """Render a naming pattern with support for zero-padding.

    Supports placeholders like {title}, {counter}, {year}, {season}, {episode}.
    For {counter:N} and {episode:N} where N is digits, applies zero padding if the value is numeric;
    otherwise uses the value as-is.
    Unknown placeholders are replaced with an empty string.
    """

    # If pattern uses Django template syntax, render via template engine for maximum flexibility.
    if ("{{" in pattern) or ("{%" in pattern):
        engine = Engine(builtins=["extract.templatetags.naming"])  # includes the 'pad' filter
        tpl = engine.from_string(pattern)
        return tpl.render(Context(values))

    # First, handle optional leading space for season/episode so we can drop the space when empty.
    def repl_opt(match: re.Match) -> str:  # type: ignore[name-defined]
        space = match.group(1) or ""
        name = match.group(2)
        width = match.group(3)
        raw = values.get(name, "")
        is_empty = raw is None or str(raw) == ""
        if is_empty:
            return ""
        if width:
            try:
                w = int(width)
            except Exception:
                w = 0
            try:
                num = int(raw)
                return (space if space else "") + str(num).zfill(w)
            except Exception:
                return (space if space else "") + str(raw)
        return (space if space else "") + str(raw)

    s = _OPT_SPACE_SEASON_EP.sub(repl_opt, pattern)

    def repl(match: re.Match) -> str:  # type: ignore[name-defined]
        name = match.group(1)
        width = match.group(2)
        raw = values.get(name, "")
        if raw is None:
            return ""
        # Zero padding only applies for numeric values and when width specified
        if width and name in {"counter", "episode", "season", "year"}:
            try:
                w = int(width)
            except Exception:
                w = 0
            # Accept int or numeric string
            try:
                num = int(raw)
                return str(num).zfill(w)
            except Exception:
                # Non-numeric, ignore padding
                return str(raw)
        return str(raw)

    # Replace remaining placeholders
    return _PLACEHOLDER_RE.sub(repl, s)
