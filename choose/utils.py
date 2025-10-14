from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, TypedDict
from urllib.parse import quote, urlencode

from django.conf import settings

from .constants import IMAGE_EXTS, SEASON_EPISODE_PATTERN
from kwc.utils.files import cache_token


def validate_folder_name(folder: str) -> str:
    """Validate and sanitize a folder name to prevent path traversal.
    
    Args:
        folder: The folder name to validate
        
    Returns:
        The sanitized folder name
        
    Raises:
        ValueError: If the folder name is invalid (contains path separators or is hidden)
    """
    safe_name = os.path.basename(folder)
    if safe_name != folder:
        raise ValueError("Invalid folder name: contains path separators")
    if safe_name.startswith('.'):
        raise ValueError("Invalid folder name: hidden folders not allowed")
    return safe_name


def get_folder_path(folder: str, root: Path | None = None) -> Path:
    """Get and validate the full path to a folder under the wallpapers root.
    
    Args:
        folder: The folder name to validate and locate
        root: Optional wallpapers root path (defaults to settings value)
        
    Returns:
        The full Path to the validated folder
        
    Raises:
        ValueError: If the folder name is invalid
        FileNotFoundError: If the folder doesn't exist or isn't a directory
    """
    safe_name = validate_folder_name(folder)
    root_path = root or wallpapers_root()
    target = root_path / safe_name
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(f"Folder not found: {safe_name}")
    return target


def parse_title_year_from_folder(folder_name: str) -> tuple[str, str | int | None]:
    """Parse title and year from a folder name like 'Title (Year)'.
    
    This is a wrapper around parse_folder_name that returns the year as-is
    (can be string or int or None) for compatibility with rename logic.
    
    Args:
        folder_name: The folder name to parse
        
    Returns:
        A tuple of (title, year) where year may be an int, empty string, or None
    """
    title, year_int = parse_folder_name(folder_name)
    return title, year_int


class MediaFolder(TypedDict):
    """Metadata describing a folder of extracted wallpapers."""

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
    return Path(settings.WALLPAPERS_FOLDER)


def parse_folder_name(folder_name: str) -> tuple[str, int | None]:
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
                except (ValueError, OverflowError):
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


def wallpaper_url(folder: str, filename: str, *, root: Path | None = None) -> str:
    """Return a cache-busted URL for a wallpaper image."""
    base = f"/wallpapers/{quote(folder)}/{quote(filename)}"
    actual_root = root or wallpapers_root()
    path = actual_root / folder / filename
    return f"{base}?v={cache_token(path)}"


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
    params['v'] = cache_token(path)

    query = urlencode(params)
    return f"{base}?{query}" if query else base


def parse_season_episode(filename: str) -> tuple[str, str]:
    """Parse season and episode from a filename.
    
    Args:
        filename: The filename to parse (e.g., "Title S01E02.jpg", "Title S01.jpg", or "Title S01EIN.jpg")
        
    Returns:
        A tuple of (season, episode) where both are strings. Returns ("", "") if no match.
        Season is numeric (e.g., "01"), episode can be numeric, special like "IN"/"OU", or empty string.
    """
    pattern = re.compile(SEASON_EPISODE_PATTERN, re.IGNORECASE)
    match = pattern.search(filename)
    if match:
        season = match.group("season")
        episode = match.group("episode") or ""  # Episode is optional, may be None
        return season, episode
    return "", ""


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

                    entry: MediaFolder = {
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
                    entries.append(entry)
        except PermissionError:
            # If the process lacks permissions, surface an empty list instead of failing.
            pass

    entries.sort(key=lambda x: (x['year_sort'], x['mtime'], x['name'].lower()), reverse=True)
    return entries, root_path
