"""
main.py

Package kwc

Created by kinami on 2023-08-06
"""

import logging
from pathlib import Path

from rich.logging import RichHandler
from typer import Typer, Option, Argument

from extract import extract as ext

app = Typer()


@app.callback()
def callback(
        verbose: bool = Option(False, "-v", "--verbose", help='Show verbose output.')
):
    logging.basicConfig(
        level="DEBUG" if verbose else "INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
    )


@app.command()
def extract(
        videos: Path = Argument(..., help='Video file to extract frames from.', exists=True),
        output: Path = Argument(..., help='Output directory.', exists=True),
        transcode: bool = Option(False, help='Transcode video before extracting frames.'),
        transcode_width: int = Option(1280, help='Width of the transcoded video.'),
        transcode_height: int = Option(720, help='Height of transcoded the video.'),
        phash_size: int = Option(64, help='Size of perceptual hash.'),
        colorhash_size: int = Option(8, help='Size of color hash.'),
        baseline_degree: int = Option(3, help='Baseline degree for peak detection.'),
        threshold: float = Option(0.2, help='Threshold for peak detection.'),
        min_distance: int = Option(10, help='Minimum distance between peaks for peak detection.'),
):
    ext(videos, transcode, transcode_width, transcode_height, phash_size, colorhash_size, baseline_degree, threshold,
        min_distance, output)


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    app()
