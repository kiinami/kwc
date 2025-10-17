"""Gallery-specific utility functions."""
from __future__ import annotations

import os
from pathlib import Path

from common.models import MediaFolder
from common.utils import (
    find_cover_filename,
    parse_folder_name,
    thumbnail_url,
    wallpaper_url,
    wallpapers_root,
)


def list_media_folders(root: Path | None = None) -> tuple[list[MediaFolder], Path]:
    """Scan the wallpapers root for folders containing wallpapers.

    Returns a tuple of (entries, root_path) where entries are sorted by
    recency and year.
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

                    folder_entry: MediaFolder = {
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
                    entries.append(folder_entry)
        except PermissionError:
            pass

    entries.sort(key=lambda x: (x['year_sort'], x['mtime'], x['name'].lower()), reverse=True)
    return entries, root_path
