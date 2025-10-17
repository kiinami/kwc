"""Shared utility functions for gallery and choose apps."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, urlencode

from django.conf import settings

from kwc.utils.files import cache_token

# Image file extensions
IMAGE_EXTS = frozenset({'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'})

# Season/episode pattern
SEASON_EPISODE_PATTERN = r'(?:S(?P<season>\d+))?(?:E(?P<episode>\d+|IN|OU))?(?<!S)(?<!E)(?:(?<=\s)E(?P<ep_only>\d+|IN|OU))?'


def wallpapers_root() -> Path:
    """Return the root directory where wallpapers are stored."""
    return Path(settings.WALLPAPERS_FOLDER)


def extract_root() -> Path:
    """Return the root directory where extracted frames are staged."""
    return Path(settings.EXTRACT_FOLDER)


def validate_folder_name(folder: str) -> str:
    """Validate and sanitize a folder name to prevent path traversal."""
    safe_name = os.path.basename(folder)
    if safe_name != folder:
        raise ValueError("Invalid folder name: contains path separators")
    if safe_name.startswith('.'):
        raise ValueError("Invalid folder name: hidden folders not allowed")
    return safe_name


def get_folder_path(folder: str, root: Path | None = None) -> Path:
    """Get and validate the full path to a folder under the given root."""
    safe_name = validate_folder_name(folder)
    root_path = root or wallpapers_root()
    target = root_path / safe_name
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(f"Folder not found: {safe_name}")
    return target


def parse_folder_name(folder_name: str) -> tuple[str, int | None]:
    """Parse a folder name like 'Title (2020)' into (title, year|None)."""
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


def parse_title_year_from_folder(folder_name: str) -> tuple[str, str | int | None]:
    """Parse title and year from a folder name."""
    title, year_int = parse_folder_name(folder_name)
    return title, year_int


def list_image_files(folder: Path) -> list[str]:
    """Return all non-hidden image filenames in a folder, sorted."""
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
    """Find cover image: .cover.* if present, else first image file."""
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
    actual_root = root or wallpapers_root()
    
    # Determine URL prefix based on root path
    extract_path = extract_root()
    if actual_root == extract_path or str(actual_root).startswith(str(extract_path)):
        base = f"/extractions/{quote(folder)}/{quote(filename)}"
    else:
        base = f"/wallpapers/{quote(folder)}/{quote(filename)}"
    
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
    """Return a cache-busted URL for a resized wallpaper thumbnail."""
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
    """Parse season and episode from a filename."""
    pattern = re.compile(SEASON_EPISODE_PATTERN, re.IGNORECASE)
    match = pattern.search(filename)
    if match:
        season = match.group("season") or ""
        episode = match.group("episode") or match.group("ep_only") or ""
        return season, episode
    return "", ""


def parse_counter(filename: str) -> str:
    """Extract the numeric counter from a wallpaper filename."""
    from common.version_utils import strip_version_suffix
    
    base_name = strip_version_suffix(filename)
    stem, _ = os.path.splitext(base_name)
    match = re.search(r"(\d+)$", stem)
    return match.group(1) if match else ""


def format_section_title(season: str, episode: str) -> str:
    """Format a human-readable section title from season/episode identifiers."""
    if not season and not episode:
        return "General"
    
    parts = []
    if season:
        try:
            season_num = int(season)
            parts.append(f"Season {season_num}")
        except ValueError:
            parts.append(f"Season {season}")
    
    if episode:
        episode_upper = episode.upper()
        if episode_upper == "IN":
            parts.append("Intro")
        elif episode_upper == "OU":
            parts.append("Outro")
        else:
            try:
                ep_num = int(episode)
                parts.append(f"Episode {ep_num}")
            except ValueError:
                parts.append(f"Episode {episode}")
    
    return " ".join(parts) if parts else "General"
