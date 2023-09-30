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
        videos: list[Path] = Argument(..., help='Video files to extract frames from.'),
        output: Path = Argument(..., help='Output directory.'),
        phash_size: int = Option(64, help='Size of perceptual hash.'),
        colorhash_size: int = Option(8, help='Size of color hash.'),
):
    ext(videos, phash_size, colorhash_size, output)


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    app()
