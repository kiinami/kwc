from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple, TypedDict
import os
import time
from urllib.parse import quote, urlencode

from django.conf import settings


# Supported image extensions (lowercase)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


class MediaFolder(TypedDict, total=False):
    """Typed representation of a media folder discovered under the wallpapers root."""

    name: str
    title: str
    year: str
    year_raw: int | None
    year_sort: int
    mtime: int
    cover_filename: str | None
    cover_url: str | None
    cover_thumb_url: str | None


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


def thumbnail_url(
    folder: str,
    filename: str | None,
    *,
    width: int | None = None,
    height: int | None = None,
    root: Path | None = None,
) -> str | None:
    """Return a cache-busted URL for a resized wallpaper thumbnail.

    Thumbnails are generated on-demand and are not persisted alongside wallpapers.
    """

    if not filename:
        return None

    base = f"/wall-thumbs/{quote(folder)}/{quote(filename)}"
    actual_root = root or wallpapers_root()
    path = actual_root / folder / filename

    params: dict[str, str] = {}
    if width and width > 0:
        params['w'] = str(width)
    if height and height > 0:
        params['h'] = str(height)
    params['v'] = _cache_token(path)

    query = urlencode(params)
    return f"{base}?{query}" if query else base


def list_media_folders(root: Path | None = None) -> tuple[list[MediaFolder], Path]:
    """Scan the wallpapers root for folders containing wallpapers.

    Returns a tuple of (entries, root_path) where entries are already sorted by
    recency and year similar to the legacy index view behaviour.
    """

    root_path = root or wallpapers_root()
    entries: list[MediaFolder] = []

    if root_path.exists() and root_path.is_dir():
        try:
            with os.scandir(root_path) as it:
                for entry in it:
                    if not entry.is_dir():
                        continue
                    if entry.name.startswith('.'):
                        continue

                    folder_name = entry.name
                    title, year_int = parse_folder_name(folder_name)
                    cover_filename = find_cover_filename(root_path / folder_name)
                    cover_url = (
                        wallpaper_url(folder_name, cover_filename, root=root_path)
                        if cover_filename
                        else None
                    )
                    cover_thumb_url = (
                        thumbnail_url(folder_name, cover_filename, width=360, root=root_path)
                        if cover_filename
                        else None
                    )

                    try:
                        mtime = entry.stat().st_mtime_ns
                    except Exception:
                        mtime = 0

                    entries.append(
                        {
                            'name': folder_name,
                            'title': title,
                            'year': str(year_int) if year_int is not None else '',
                            'year_raw': year_int,
                            'year_sort': year_int if year_int is not None else -1,
                            'mtime': mtime,
                            'cover_filename': cover_filename,
                            'cover_url': cover_url,
                            'cover_thumb_url': cover_thumb_url,
                        }
                    )
        except PermissionError:
            # If the process lacks permissions, surface an empty list instead of failing.
            pass

    entries.sort(key=lambda x: (x['year_sort'], x['mtime'], x['name'].lower()), reverse=True)
    return entries, root_path
