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
from rich.progress import Progress
from vidgear.gears import CamGear

logger = logging.getLogger(__name__)


def total_frames(video: Path) -> int:
    cap = cv2.VideoCapture(str(video))
    return int(cap.get(cv2.CAP_PROP_FRAME_COUNT))


def scale(img, xScale, yScale):
    return cv2.resize(img, None, fx=xScale, fy=yScale, interpolation=cv2.INTER_AREA)


def grayscale(frame):
    grayframe = None
    gray = None
    if frame is not None:
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = scale(gray, 1, 1)
        grayframe = scale(gray, 1, 1)
        gray = cv2.GaussianBlur(gray, (9, 9), 0.0)
    return grayframe, gray


def save_frame(frame, output: Path, i: int):
    cv2.imwrite(str(output / f'{i}.jpg'), frame)


def extract(
        videos: list[Path],
        output: Path
):
    logger.info(f'Extracting frames from {len(videos)} videos to {output}...')
    i = 0
    video = videos[0]
    diff = []
    last = None
    with Progress() as progress:
        task = progress.add_task(f'Analyzing {video}', total=total_frames(video))
        stream = CamGear(source=str(video), logging=True).start()

        while True:
            frame = stream.read()
            if frame is None:
                stream.stop()
                break

            gray, gray_blur = grayscale(frame)
            if last is None:
                last = gray_blur

            diff.append(cv2.countNonZero(cv2.subtract(gray_blur, last)))

            i += 1
            progress.update(task, completed=i)

    logger.info(f'Analyzed {i} frames.')

    y = np.array(diff)
    base = peakutils.baseline(y, 2)
    indices = peakutils.indexes(y - base, 0.3, min_dist=1)

    i = 0
    with Progress() as progress:
        task = progress.add_task(f'Extracting frames from {video}', total=len(indices))
        stream = CamGear(source=str(video), logging=True).start()

        while True:
            frame = stream.read()
            if frame is None:
                stream.stop()
                break

            if i in indices:
                save_frame(frame, output, i)
                progress.update(task, completed=i)

            i += 1
