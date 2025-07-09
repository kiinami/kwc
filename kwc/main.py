"""
main.py

Package kwc

Created by kinami on 2023-08-06
"""

import logging
from enum import Enum
from pathlib import Path
from typing import Annotated

from rich.logging import RichHandler
from typer import Typer, Option, Argument

from kwc.extract import extract_custom, extract_ffmpeg
from kwc.select import select as sel

app = Typer()


@app.callback()
def callback(
        verbose: bool = Option(False, "-v", "--verbose", help='Show verbose output.')
):
    logging.basicConfig(
        level="DEBUG" if verbose else "INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
    )


class Extractor(str, Enum):
    custom = 'custom'
    ffmpeg = 'ffmpeg'


@app.command()
def extract(
        video: Path = Argument(..., help='Video file to extract frames from.', exists=True),
        output: Path = Argument(..., help='Output directory.', exists=True),
        algorithm: Annotated[
            Extractor, Option(case_sensitive=False)
        ] = Extractor.ffmpeg,
        trim_start: str = Option(None, help='Start time for trimming, in HH:MM:SS format.'),
        trim_end: str = Option(None, help='End time for trimming, in HH:MM:SS format.'),
        transcode: bool = Option(False, help='Transcode video before extracting frames.'),
        transcode_width: int = Option(1280, help='Width of the transcoded video.'),
        transcode_height: int = Option(720, help='Height of transcoded the video.'),
        phash_size: int = Option(64, help='Size of perceptual hash.'),
        colorhash_size: int = Option(8, help='Size of color hash.'),
        baseline_degree: int = Option(3, help='Baseline degree for peak detection.'),
        threshold: float = Option(0.2, help='Threshold for peak detection.'),
        min_distance: int = Option(10, help='Minimum distance between peaks for peak detection.'),
):
    if algorithm == Extractor.ffmpeg:
        extract_ffmpeg(video, output)
    elif algorithm == Extractor.custom:
        extract_custom(video, trim_start, trim_end, transcode, transcode_width, transcode_height, phash_size, colorhash_size,
        baseline_degree, threshold, min_distance, output)


@app.command()
def select(
        directory: Path = Argument(..., help='Directory containing images to select.'),
        selected: Path = Option('./selected', help='Directory to move selected images to.'),
        discarded: Path = Option('./discarded', help='Directory to move discarded images to.')
):
    sel(directory, selected, discarded)


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    app()
