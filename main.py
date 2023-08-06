"""
main.py

Package kwc

Created by kinami on 2023-08-06
"""

import logging
from typer import Typer


app = Typer()


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    app()
