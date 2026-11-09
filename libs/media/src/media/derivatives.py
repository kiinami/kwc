"""Disposable AVIF derivatives for the browser."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import pillow_avif  # noqa: F401  (registers the AVIF plugin with Pillow)
import pillow_jxl  # noqa: F401  (registers the JXL plugin with Pillow)
from PIL import Image, ImageOps

from .jxl import probe_dimensions

_ENCODE_SEMAPHORE = threading.Semaphore(2)


class DerivativeCache:
    def __init__(
        self,
        root: Path,
        *,
        max_bytes: int,
        thumb_width: int = 480,
        lens_long_edge: int = 1920,
        pixel_budget: int = 100_000_000,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.thumb_width = thumb_width
        self.lens_long_edge = lens_long_edge
        self.pixel_budget = pixel_budget

    def thumb(self, source: Path, key: str) -> Path:
        return self._ensure(source, key, width=self.thumb_width, long_edge=None, kind="thumb")

    def lens(self, source: Path, key: str) -> Path:
        return self._ensure(source, key, width=None, long_edge=self.lens_long_edge, kind="lens")

    def _ensure(self, source: Path, key: str, *, width: int | None, long_edge: int | None, kind: str) -> Path:
        stat = source.stat()
        digest = hashlib.sha256(
            f"{key}|{stat.st_mtime_ns}|{stat.st_size}|{width}|{long_edge}|{kind}".encode()
        ).hexdigest()
        destination = self.root / digest[:2] / f"{digest}.avif"
        if destination.exists():
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        with _ENCODE_SEMAPHORE:
            if destination.exists():
                return destination
            self._render(source, destination, width=width, long_edge=long_edge)
        self._evict()
        return destination

    def _render(self, source: Path, destination: Path, *, width: int | None, long_edge: int | None) -> None:
        temporary = destination.with_suffix(".tmp")
        try:
            source_width, source_height = probe_dimensions(source)
            if source_width * source_height > self.pixel_budget:
                self._placeholder(temporary, width if width is not None else long_edge or self.thumb_width)
            else:
                with Image.open(source) as image:
                    image = ImageOps.exif_transpose(image)
                    if width is not None:
                        image.thumbnail((width, 10**9), Image.Resampling.LANCZOS)
                    elif long_edge is not None:
                        image.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
                    image.convert("RGB").save(temporary, format="AVIF", quality=80)
        except Exception:
            self._placeholder(temporary, width if width is not None else long_edge or self.thumb_width)
        temporary.replace(destination)

    def _placeholder(self, destination: Path, target_width: int) -> None:
        side = max(1, int(self.pixel_budget**0.5))
        width = max(1, min(target_width, side))
        height = max(1, width * 9 // 16)
        Image.new("RGB", (width, height), (20, 22, 26)).save(destination, format="AVIF", quality=70)

    def _evict(self) -> None:
        files = sorted(self.root.rglob("*.avif"), key=lambda path: path.stat().st_mtime_ns)
        total = sum(path.stat().st_size for path in files)
        for path in files:
            if total <= self.max_bytes:
                break
            total -= path.stat().st_size
            path.unlink(missing_ok=True)
