"""Shared thumbnail generation utilities."""
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageOps

# Thumbnail configuration
THUMB_MAX_DIMENSION = 2048
THUMB_CACHE_SIZE = 256


class _ThumbResult(NamedTuple):
    """Result of thumbnail generation."""
    data: bytes
    content_type: str


def sanitize_dimension(value: str | None) -> int:
    """Sanitize and validate a dimension parameter."""
    if not value:
        return 0
    try:
        dim = int(value)
    except (TypeError, ValueError):
        return 0
    if dim <= 0:
        return 0
    return max(16, min(dim, THUMB_MAX_DIMENSION))


@lru_cache(maxsize=THUMB_CACHE_SIZE)
def render_thumbnail_cached(path_str: str, width: int, height: int, mtime_ns: int) -> _ThumbResult:
    """Generate and cache a thumbnail for an image.
    
    Args:
        path_str: Path to the source image
        width: Maximum width (0 for no limit)
        height: Maximum height (0 for no limit)
        mtime_ns: Modification time in nanoseconds (for cache busting)
        
    Returns:
        Thumbnail data and content type
    """
    path = Path(path_str)
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        max_w = width if width > 0 else THUMB_MAX_DIMENSION
        max_h = height if height > 0 else THUMB_MAX_DIMENSION
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

        has_alpha = img.mode in ("LA", "RGBA") or (img.mode == "P" and "transparency" in img.info)
        buffer = BytesIO()
        if has_alpha:
            if img.mode not in ("LA", "RGBA"):
                img = img.convert("RGBA")
            img.save(buffer, "PNG", optimize=True)
            content_type = "image/png"
        else:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            elif img.mode == "L":
                img = img.convert("RGB")
            img.save(buffer, "JPEG", quality=82, optimize=True, progressive=True)
            content_type = "image/jpeg"

    return _ThumbResult(buffer.getvalue(), content_type)
