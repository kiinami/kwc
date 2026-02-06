from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict
from urllib.parse import quote, urlencode

from django.conf import settings

from kwc.utils.files import cache_token

from .constants import IMAGE_EXTS, SEASON_EPISODE_PATTERN


def parse_version_suffix(filename: str) -> tuple[str, str]:
    """Parse version suffix from a filename.

    Version suffixes are 1-2 uppercase ASCII letters appended before the extension,
    after the counter. They must not repeat letters.

    Examples:
        "Title ~ 0001.jpg" -> ("", "")
        "Title ~ 0001U.jpg" -> ("U", "")
        "Title ~ 0001UM.jpg" -> ("UM", "")
        "Title ~ 0001e.jpg" -> ("", "e")  # invalid: lowercase
        "Title ~ 0001EE.jpg" -> ("", "EE")  # invalid: repeated
        "Title ~ 0001EPU.jpg" -> ("", "EPU")  # invalid: too long

    Args:
        filename: The filename to parse

    Returns:
        A tuple of (valid_suffix, invalid_suffix) where at most one is non-empty.
        If the suffix is valid, it's in the first element. If invalid, it's in the second.
    """
    # Get the stem (filename without extension)
    stem = os.path.splitext(filename)[0]

    # Pattern to match suffix: 1-2 characters at the end of the stem
    # We look for sequences of letters after the last number/space/tilde
    match = re.search(r"([A-Za-z]{1,3})$", stem)

    if not match:
        return ("", "")

    suffix = match.group(1)

    # Validate suffix:
    # 1. Must be 1-2 characters
    if len(suffix) > 2:
        return ("", suffix)

    # 2. Must be all uppercase
    if not suffix.isupper():
        return ("", suffix)

    # 3. Must not have repeated letters
    if len(suffix) != len(set(suffix)):
        return ("", suffix)

    return (suffix, "")


def strip_version_suffix(filename: str) -> str:
    """Remove version suffix from a filename, returning the base filename.

    Args:
        filename: The filename to strip

    Returns:
        The filename without any valid or invalid version suffix
    """
    stem = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1]

    # Remove any suffix (valid or invalid) that matches our pattern
    stem_without_suffix = re.sub(r"[A-Za-z]{1,3}$", "", stem)

    return stem_without_suffix + ext


def add_version_suffix(filename: str, suffix: str) -> str:
    """Add a version suffix to a filename.

    Args:
        filename: The base filename (should not already have a suffix)
        suffix: The suffix to add (1-2 uppercase letters)

    Returns:
        The filename with the suffix added before the extension
    """
    stem = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1]

    if not suffix:
        return filename

    return stem + suffix + ext


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
    if safe_name.startswith("."):
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


def extraction_root() -> Path:
    """Return the inbox directory for new extractions.

    Configured via settings.EXTRACTION_FOLDER.
    """
    return Path(settings.EXTRACTION_FOLDER)


def discard_root() -> Path:
    """Return the trash directory for discarded images.

    Configured via settings.DISCARD_FOLDER.
    """
    return Path(settings.DISCARD_FOLDER)


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
            if e.is_file() and not e.name.startswith("."):
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
    actual_root = root or wallpapers_root()

    # Check if we are serving from the inbox
    if actual_root == extraction_root():
        base = f"/inbox-files/{quote(folder)}/{quote(filename)}"
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
    """Return a cache-busted URL for a resized wallpaper thumbnail.

    Thumbnails are generated on-demand and are not persisted alongside wallpapers.
    """

    if not filename:
        return None

    actual_root = root or wallpapers_root()

    if actual_root == extraction_root():
        base = f"/inbox-thumbs/{quote(folder)}/{quote(filename)}"
    else:
        base = f"/wall-thumbs/{quote(folder)}/{quote(filename)}"

    path = actual_root / folder / filename

    params: dict[str, str] = {}
    if width and width > 0:
        params["w"] = str(width)
    if height and height > 0:
        params["h"] = str(height)
    params["v"] = cache_token(path)

    query = urlencode(params)
    return f"{base}?{query}" if query else base


def parse_counter(filename: str) -> str:
    """Extract the numeric counter from a wallpaper filename.

    Args:
        filename: The filename to parse (e.g., "Title 〜 0001.jpg", "Title 〜 0001U.jpg").

    Returns:
        The counter portion as a string (including any padding) or an empty string if
        no counter could be identified.
    """

    # Remove any valid/invalid version suffix to keep only the base name and counter
    base_name = strip_version_suffix(filename)
    stem, _ = os.path.splitext(base_name)

    match = re.search(r"(\d+)$", stem)
    return match.group(1) if match else ""


def parse_season_episode(filename: str) -> tuple[str, str]:
    """Parse season and episode from a filename.

    Args:
        filename: The filename to parse (e.g., "Title S01E02.jpg", "Title S01.jpg", "Title E01.jpg", or "Title EIN.jpg")

    Returns:
        A tuple of (season, episode) where both are strings. Returns ("", "") if no match.
        Season can be numeric (e.g., "01") or empty (for episode-only).
        Episode can be numeric, special like "IN"/"OU", or empty string (for season-only).
    """
    pattern = re.compile(SEASON_EPISODE_PATTERN, re.IGNORECASE)
    match = pattern.search(filename)
    if match:
        season = match.group("season") or ""  # Season is optional, may be None
        # Episode can be in either "episode" group (when season present) or "ep_only" group
        episode = match.group("episode") or match.group("ep_only") or ""
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
                    if entry.name.startswith("."):
                        continue

                    folder_name = entry.name
                    title, year_int = parse_folder_name(folder_name)
                    cover_filename = find_cover_filename(root_path / folder_name)
                    cover_url = wallpaper_url(folder_name, cover_filename, root=root_path) if cover_filename else None
                    cover_thumb_url = (
                        thumbnail_url(folder_name, cover_filename, width=360, root=root_path)
                        if cover_filename
                        else None
                    )

                    try:
                        mtime = entry.stat().st_mtime_ns
                    except Exception:
                        mtime = 0

                    entry: MediaFolder = {  # type: ignore[no-redef]
                        "name": folder_name,
                        "title": title,
                        "year": str(year_int) if year_int is not None else "",
                        "year_raw": year_int,
                        "year_sort": year_int if year_int is not None else -1,
                        "mtime": mtime,
                        "cover_filename": cover_filename,
                        "cover_url": cover_url,
                        "cover_thumb_url": cover_thumb_url,
                    }
                    entries.append(entry)  # type: ignore[arg-type]
        except PermissionError:
            # If the process lacks permissions, surface an empty list instead of failing.
            pass

    entries.sort(key=lambda x: (x["year_sort"], x["mtime"], x["name"].lower()), reverse=True)
    return entries, root_path
