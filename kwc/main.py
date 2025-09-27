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
        selected: Path = Option(None, help='Directory to move selected images to.'),
        discarded: Path = Option(None, help='Directory to move discarded images to.')
):
    """Classify images in a directory into selected and discarded with a GUI."""
    from kwc.select import select as sel
    if not selected:
        selected = directory / 'selected'
    if not discarded:
        discarded = directory / 'discarded'
    sel(directory, selected, discarded)

models = Enum('Models', {model.replace("-", "_"): model for model in pyanime4k.pyac.specs.ModelNameList})
processors = Enum('Processors', {proc.replace("-", "_"): proc for proc in pyanime4k.pyac.specs.ProcessorNameList})

@app.command()
def upscale(
    directory: Path = Argument(..., help='Directory containing images to upscale.'),
    scale: Annotated[float, Option("-s", "--scale", help='Scale factor for upscaling images.')] = 2.0,
    model: Annotated[models, Option("-m", "--model", help='Model to use for upscaling.')] = models.acnet_gan,
    processor: Annotated[processors, Option("-p", "--processor", help='Processor to use for upscaling (e.g., "opencl", "cpu").')] = processors.opencl,
    suffix: Annotated[str, Option("-S", "--suffix", help='Suffix to append to upscaled images.')] = 'U'
):
    """Upscale images in a directory using a specified model."""
    from kwc.upscale import upscale
    upscale(directory, scale, model, processor, suffix)

if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    app()
