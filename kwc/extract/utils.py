from pathlib import Path

import cv2


def total_frames(video: Path) -> int:
    cap = cv2.VideoCapture(str(video))
    return int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
