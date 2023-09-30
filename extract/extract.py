"""
extract.py

Package extract

Created by kinami on 2023-08-06
"""

import logging
from pathlib import Path

import cv2
import numpy as np
import peakutils
from PIL import Image
from imagehash import phash, colorhash
from rich.progress import Progress
from vidgear.gears import CamGear

logger = logging.getLogger(__name__)


def total_frames(video: Path) -> int:
    cap = cv2.VideoCapture(str(video))
    return int(cap.get(cv2.CAP_PROP_FRAME_COUNT))


def hashdiff(phash1, phash2):
    return phash1 - phash2


def save_frame(frame, output: Path, i: int):
    cv2.imwrite(str(output / f'{i}.jpg'), frame)


def extract(
        videos: list[Path],
        phash_size: int,
        colorhash_size: int,
        output: Path
):
    logger.info(f'Extracting frames from {len(videos)} videos to {output}...')
    i = 0
    video = videos[0]
    pls = []
    cls = []
    total = total_frames(video)
    with Progress(transient=True) as progress:
        task = progress.add_task(f'Analyzing {video}', total=total)
        stream = CamGear(source=str(video), logging=False).start()

        while True:
            frame = stream.read()
            if frame is None:
                stream.stop()
                break

            img = Image.fromarray(frame)

            pls.append(phash(img, hash_size=phash_size))
            cls.append(colorhash(img, binbits=colorhash_size))

            i += 1
            progress.update(task, completed=i)

        logger.debug(f'Analyzed {i} frames in {progress.get_time()}.')

    pdiff = []
    cdiff = []
    for i in range(len(pls) - 1):
        pdiff.append(hashdiff(pls[i], pls[i + 1]))
        cdiff.append(hashdiff(cls[i], cls[i + 1]))

    y = np.multiply(np.array(pdiff), np.array(cdiff))
    base = peakutils.baseline(y, 2)
    indices = peakutils.indexes(y - base, 0.2, min_dist=10)

    i = 0
    with Progress(transient=True) as progress:
        task = progress.add_task(f'Extracting frames from {video}', total=len(indices))
        stream = CamGear(source=str(video), logging=False).start()

        while True:
            frame = stream.read()
            if frame is None:
                stream.stop()
                break

            if i in indices:
                save_frame(frame, output, i)

            progress.update(task, completed=i)
            i += 1

    logger.info(f'Selected {len(indices)} from {total} frames ({len(indices) / total * 100:.2f}%).')
