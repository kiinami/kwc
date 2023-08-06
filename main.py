"""
main.py

Package kwc

Created by kinami on 2023-08-06
"""

import logging

from rich.logging import RichHandler
from typer import Typer, Option

app = Typer()


@app.callback()
def callback(
        verbose: bool = Option(False, "-v", "--verbose", help='Show verbose output.')
):
    logging.basicConfig(
        level="DEBUG" if verbose else "INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
    )


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    app()
