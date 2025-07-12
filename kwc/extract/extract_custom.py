"""
extract.py

Package extract

Created by kinami on 2023-08-06
"""
import logging
import multiprocessing as mp
import os
from datetime import timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2
import numpy as np
import peakutils
from PIL import Image
from cachier import cachier, set_global_params as set_global_cachier_params
from imagehash import phash, colorhash
from rich.progress import Progress, MofNCompleteColumn, TimeElapsedColumn
from vidgear.gears import CamGear

from .utils import total_frames, trim_video, transcode_video

logger = logging.getLogger(__name__)
set_global_cachier_params(
    separate_files=True,
    stale_after=timedelta(days=7),
)


def score(img: np.ndarray):
    return cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_16S).var()


def hashdiff(phash1, phash2):
    return phash1 - phash2


@cachier()
def process_frame(frame, phash_size, colorhash_size):
    img = Image.fromarray(frame)
    return phash(img, hash_size=phash_size), colorhash(img, binbits=colorhash_size), score(frame)


def save_frame(frame, output: Path, name: str, i: int):
    cv2.imwrite(str(output / f'{name}_{i}.jpg'), frame)


def frame_reader(video, frame_queue, stop_event):
    stream = CamGear(source=str(video), logging=False).start()
    while not stop_event.is_set():
        frame = stream.read()
        if frame is None:
            break
        frame_queue.put(frame)
    stream.stop()
    frame_queue.put(None)  # Signal the end of the stream


def frame_worker(frame_queue, result_queue, phash_size, colorhash_size, stop_event):
    while not stop_event.is_set():
        frame = frame_queue.get()
        if frame is None:
            result_queue.put(None)  # Signal the end of processing
            break
        result = process_frame(frame, phash_size, colorhash_size)
        result_queue.put(result)


def analyze_frames(video, phash_size, colorhash_size):
    i = 0
    pls = []
    cls = []
    sls = []
    total = total_frames(video)
    frame_queue = mp.Queue(maxsize=15)  # Bounded queue to limit memory usage
    result_queue = mp.Queue()
    stop_event = mp.Event()

    with Progress(*Progress.get_default_columns(), TimeElapsedColumn(), MofNCompleteColumn(),
                  transient=True) as progress:
        task = progress.add_task(f'Analyzing {video}', total=total)

        reader_process = mp.Process(target=frame_reader, args=(video, frame_queue, stop_event))
        reader_process.start()
        pool = mp.Pool(mp.cpu_count(), frame_worker,
                       (frame_queue, result_queue, phash_size, colorhash_size, stop_event))
        while True:
            result = result_queue.get()
            if result is None:
                break
            p_hash, c_hash, s = result
            pls.append(p_hash)
            cls.append(c_hash)
            sls.append(s)
            i += 1
            progress.update(task, completed=i)

        stop_event.set()
        reader_process.join()
        pool.terminate()
        pool.join()
    return pls, cls, sls


@cachier()
def select_frames(pls, cls, sls, baseline_degree, threshold, min_distance):
    pdiff = []
    cdiff = []
    for i in range(len(pls) - 1):
        pdiff.append(hashdiff(pls[i], pls[i + 1]))
        cdiff.append(hashdiff(cls[i], cls[i + 1]))

    y = np.multiply(np.array(pdiff), np.array(cdiff))
    base = peakutils.baseline(y, deg=baseline_degree)
    peaks = peakutils.indexes(y - base, threshold, min_dist=min_distance)

    indices = [
        max(range(i + 1, j), key=lambda k: sls[k])
        for i, j in zip([0, *peaks], [*peaks, len(sls) - 1])
    ]
    return indices


def extract_frames(video, output, indices, name: str):
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
                save_frame(frame, output, name, i)

            i += 1

            if i in indices:
                progress.update(task, completed=i)

    logger.info(f'Extracted {len(indices)} frames to "{output.absolute()}".')


def extract_custom(
        video: Path,
        trim_start: str,
        trim_end: str,
        transcode: bool,
        transcode_width: int,
        transcode_height: int,
        phash_size: int,
        colorhash_size: int,
        baseline_degree: int,
        threshold: float,
        min_distance: int,
        output: Path
):
    if not output.exists():
        output.mkdir(parents=True, exist_ok=True)

    logger.info(f'Extracting frames from "{video.absolute()}" to "{output.absolute()}"...')
    video_name = video.stem
    if trim_start or trim_end:
        video_tmpfile = NamedTemporaryFile(delete=False, suffix=video.suffix)
        video_tmpfile.close()
        trim_video(video, Path(video_tmpfile.name), trim_start, trim_end)
        video = Path(video_tmpfile.name)

    if transcode:
        with NamedTemporaryFile(suffix='.mp4') as tmp:
            lowres_video = Path(tmp.name)
            transcode_video(video, lowres_video, transcode_width, transcode_height, trim_start, trim_end)
            logger.info(f'Transcoded "{video.absolute()}" to "{lowres_video.absolute()}"')
            pls, cls, sls = analyze_frames(lowres_video, phash_size, colorhash_size)
    else:
        pls, cls, sls = analyze_frames(video, phash_size, colorhash_size)
    logger.info(f'Analyzed {len(pls)} frames.')

    selected_frames = select_frames(pls, cls, sls, baseline_degree, threshold, min_distance)
    logger.info(
        f'Selected {len(selected_frames)} from {len(pls)} frames ({len(selected_frames) / len(pls) * 100:.2f}%).')
    extract_frames(video, output, selected_frames, video_name)

    if trim_start or trim_end:
        os.remove(video_tmpfile.name)
