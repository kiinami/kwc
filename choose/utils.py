from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple
import os
import time
from urllib.parse import quote

from django.conf import settings


# Supported image extensions (lowercase)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def wallpapers_root() -> Path:
    """Return the root directory where wallpapers are stored.

    Configured via settings.WALLPAPERS_FOLDER and defaults to BASE_DIR / 'extracted'.
    """
    return Path(getattr(settings, "WALLPAPERS_FOLDER", settings.BASE_DIR / "extracted"))


def parse_folder_name(folder_name: str) -> Tuple[str, int | None]:
    """Parse a folder name like "Title (2020)" into (title, year|None).

    If no year suffix exists, returns the whole name as title and year=None.
    """
    title = folder_name
    year: int | None = None
    if folder_name.endswith(")"):
        left = folder_name.rfind(" (")
        if left != -1:
            maybe_year = folder_name[left + 2 : -1]
            if maybe_year.isdigit():
                title = folder_name[:left]
                try:
                    year = int(maybe_year)
                except Exception:
                    year = None
    return title, year


def list_image_files(folder: Path) -> list[str]:
    """Return all non-hidden image filenames in a folder, sorted case-insensitively."""
    files: list[str] = []
    with os.scandir(folder) as it:
        for e in it:
            if e.is_file() and not e.name.startswith('.'):
                _, ext = os.path.splitext(e.name)
                if ext.lower() in IMAGE_EXTS:
                    files.append(e.name)
    files.sort(key=lambda n: n.lower())
    return files


def find_cover_filename(folder: Path, files: Iterable[str] | None = None) -> str | None:
    """Heuristic cover image: .cover.* if present, else first image file."""
    for cand in (".cover.jpg", ".cover.jpeg", ".cover.png", ".cover.webp"):
        p = folder / cand
        if p.exists() and p.is_file():
            return p.name
    if files is None:
        try:
            files = list_image_files(folder)
        except PermissionError:
            return None
    for name in files:
        return name
    return None


def _cache_token(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return f"{int(time.time() * 1_000_000):x}"
    ino = getattr(stat, "st_ino", 0)
    return f"{stat.st_mtime_ns:x}-{stat.st_size:x}-{ino:x}"


def wallpaper_url(folder: str, filename: str, *, root: Path | None = None) -> str:
    """Return a cache-busted URL for a wallpaper image."""
    base = f"/wallpapers/{quote(folder)}/{quote(filename)}"
    actual_root = root or wallpapers_root()
    path = actual_root / folder / filename
    return f"{base}?v={_cache_token(path)}"
