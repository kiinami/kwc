"""JPEG XL encode and probe helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import pillow_jxl  # noqa: F401  (registers the JXL plugin with Pillow)
from PIL import Image

_SIZE_RE = re.compile(r"(\d+)x(\d+)")
DEFAULT_PIXEL_BUDGET = 500_000_000


class ImageTooLarge(ValueError):
    """The source exceeds the configured decode budget."""


def _normalize(image: Image.Image) -> Image.Image:
    if image.mode in {"RGB", "RGBA", "L", "LA", "I;16", "F"}:
        return image
    if image.mode in {"P", "PA"} or "transparency" in image.info:
        return image.convert("RGBA")
    return image.convert("RGB")


def encode_jxl(
    source: Path,
    dest: Path,
    *,
    lossless: bool = True,
    pixel_budget: int = DEFAULT_PIXEL_BUDGET,
) -> None:
    width, height = probe_dimensions(source)
    if width * height > pixel_budget:
        raise ImageTooLarge(f"{source.name} is {width}x{height}, over the {pixel_budget} pixel budget")
    with Image.open(source) as image:
        _normalize(image).save(dest, format="JXL", lossless=lossless)


def encode_jxl_bytes(
    data: bytes,
    dest: Path,
    *,
    lossless: bool = True,
    pixel_budget: int = DEFAULT_PIXEL_BUDGET,
) -> None:
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > pixel_budget:
            raise ImageTooLarge(f"image is {image.width}x{image.height}, over the {pixel_budget} pixel budget")
        _normalize(image).save(dest, format="JXL", lossless=lossless)


def probe_dimensions(path: Path) -> tuple[int, int]:
    if shutil.which("jxlinfo"):
        result = subprocess.run(["jxlinfo", str(path)], capture_output=True, text=True, timeout=60, check=False)
        match = _SIZE_RE.search(result.stdout)
        if result.returncode == 0 and match:
            return int(match.group(1)), int(match.group(2))
    with Image.open(path) as image:
        return image.size
