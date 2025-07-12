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
        video: Path = Argument(..., help='Video file to extract frames from.', exists=True, dir_okay=False),
        output: Path = Argument(..., help='Output directory.'),
        transcode: Annotated[bool, Option(help='Transcode video to a specific resolution before extracting frames.')] = False,
        transcode_width: Annotated[int, Option(help='Width of the transcoded video.')] = 1920,
        transcode_height: Annotated[int, Option(help='Height of the transcoded video.')] = 1080,
        trim_intervals: Annotated[list[str], Option(help='Trim intervals in the format "start-end" (e.g., "00:00:10-00:00:20").')] = None,
):
    """Extract frames from a video file."""
    from kwc.extract import extract
    extract(video, output, transcode, transcode_width, transcode_height, trim_intervals)


@app.command()
def select(
        directory: Path = Argument(..., help='Directory containing images to select.'),
        selected: Path = Option('./selected', help='Directory to move selected images to.'),
        discarded: Path = Option('./discarded', help='Directory to move discarded images to.')
):
    """Classify images in a directory into selected and discarded with a GUI."""
    from kwc.select import select as sel
    sel(directory, selected, discarded)


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    app()
