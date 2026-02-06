import hashlib
import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def calculate_image_hash(file_path: str | Path, block_size: int = 65536) -> str:
    """Calculate SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            sha256.update(block)
    return sha256.hexdigest()


def get_image_metadata(file_path: str | Path) -> tuple[int, int, int]:
    """
    Get image file size and resolution.
    Returns: (file_size_bytes, width, height)
    """
    path = Path(file_path)
    file_size = path.stat().st_size
    
    # We load the image just to get dimensions. For optimization, 
    # if we already load it elsewhere, we should pass the loaded image.
    # But for now, we follow the simple utility pattern.
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Could not read image: {file_path}")
    
    height, width = img.shape[:2]
    return file_size, width, height


def calculate_sharpness(file_path: str | Path) -> float:
    """
    Calculate image sharpness using the variance of the Laplacian.
    Higher values indicate sharper images.
    """
    img = cv2.imread(str(file_path))
    if img is None:
        logger.warning(f"Could not read image for sharpness: {file_path}")
        return 0.0

    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # variance of Laplacian corresponds to the amount of edges found in the image
        score = cv2.Laplacian(gray, cv2.CV_64F).var()
        return float(score)
    except Exception as e:
        logger.error(f"Error calculating sharpness for {file_path}: {e}")
        return 0.0


def calculate_brightness(file_path: str | Path) -> float:
    """
    Calculate average image brightness (0-255).
    """
    img = cv2.imread(str(file_path))
    if img is None:
        logger.warning(f"Could not read image for brightness: {file_path}")
        return 0.0

    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        score = np.mean(gray)
        return float(score)
    except Exception as e:
        logger.error(f"Error calculating brightness for {file_path}: {e}")
        return 0.0
