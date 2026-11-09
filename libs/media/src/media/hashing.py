"""Content and perceptual hashes."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pillow_jxl  # noqa: F401  (registers the JXL plugin with Pillow)
from PIL import Image


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def perceptual_hash(path: Path) -> str:
    """64-bit difference hash over a 9x8 grayscale thumbnail."""
    with Image.open(path) as image:
        small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = small.tobytes()
    bits = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            bits = (bits << 1) | (pixels[offset + column] < pixels[offset + column + 1])
    return f"{bits:016x}"
