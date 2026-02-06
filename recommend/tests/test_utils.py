import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from recommend.utils import (
    calculate_brightness,
    calculate_image_hash,
    calculate_sharpness,
    get_image_metadata,
)


@pytest.fixture
def temp_image_files():
    """Create temporary image files for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dir_path = Path(tmpdir)
        
        # 1. Black image (Brightness ~0)
        black_img = np.zeros((100, 100, 3), dtype=np.uint8)
        black_path = dir_path / "black.jpg"
        cv2.imwrite(str(black_path), black_img)
        
        # 2. White image (Brightness ~255)
        white_img = np.full((100, 100, 3), 255, dtype=np.uint8)
        white_path = dir_path / "white.jpg"
        cv2.imwrite(str(white_path), white_img)
        
        # 3. Noise image (High sharpness)
        np.random.seed(42)
        noise_img = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)
        noise_path = dir_path / "noise.jpg"
        cv2.imwrite(str(noise_path), noise_img)
        
        # 4. Blur image (Low sharpness)
        blur_img = cv2.GaussianBlur(noise_img, (15, 15), 0)
        blur_path = dir_path / "blur.jpg"
        cv2.imwrite(str(blur_path), blur_img)
        
        yield {
            "black": black_path,
            "white": white_path,
            "noise": noise_path,
            "blur": blur_path,
        }


def test_calculate_brightness(temp_image_files):
    # Expectation: Black should be near 0
    assert calculate_brightness(temp_image_files["black"]) < 1.0
    
    # Expectation: White should be near 255
    assert calculate_brightness(temp_image_files["white"]) > 254.0
    
    # Expectation: Noise should be somewhere in middle (avg of random uniform 0-255 is ~127.5)
    # We check a reasonable range
    noise_brightness = calculate_brightness(temp_image_files["noise"])
    assert 100 < noise_brightness < 155


def test_calculate_sharpness(temp_image_files):
    noise_sharpness = calculate_sharpness(temp_image_files["noise"])
    blur_sharpness = calculate_sharpness(temp_image_files["blur"])
    flat_sharpness = calculate_sharpness(temp_image_files["black"])
    
    # Noise should be much sharper than blur
    assert noise_sharpness > blur_sharpness
    
    # Flat image should have near zero sharpness
    assert flat_sharpness < 1.0


def test_get_image_metadata(temp_image_files):
    path = temp_image_files["black"]
    size, width, height = get_image_metadata(path)
    
    assert width == 100
    assert height == 100
    assert size > 0


def test_calculate_image_hash(temp_image_files):
    path1 = temp_image_files["black"]
    path2 = temp_image_files["white"]
    
    hash1 = calculate_image_hash(path1)
    hash2 = calculate_image_hash(path2)
    
    assert len(hash1) == 64  # SHA256 hex length
    assert hash1 != hash2
    
    # Same file same hash
    assert calculate_image_hash(path1) == hash1
