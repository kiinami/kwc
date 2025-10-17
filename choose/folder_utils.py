"""Choose app utilities for listing extraction folders."""
from __future__ import annotations

import os
import re
from pathlib import Path

from common.models import ExtractFolder
from common.utils import (
    extract_root,
    find_cover_filename,
    list_image_files,
    parse_season_episode,
    thumbnail_url,
    wallpaper_url,
)


def list_extract_folders(root: Path | None = None) -> tuple[list[ExtractFolder], Path]:
    """Scan the extract root for folders containing extracted frames.
    
    Returns a tuple of (entries, root_path) where entries are sorted by recency.
    """
    root_path = root or extract_root()
    entries: list[ExtractFolder] = []
    
    if root_path.exists() and root_path.is_dir():
        try:
            with os.scandir(root_path) as it:
                for entry in it:
                    if not entry.is_dir():
                        continue
                    if entry.name.startswith('.'):
                        continue
                    
                    folder_name = entry.name
                    
                    # Parse title, season, episode from folder name
                    season, episode = parse_season_episode(folder_name)
                    
                    # Extract title (everything before season/episode markers)
                    title = folder_name
                    if season or episode:
                        pattern = r'\s+S\d+|\s+E[A-Z0-9]+|\s+S\d+E[A-Z0-9]+'
                        title = re.sub(pattern, '', folder_name, flags=re.IGNORECASE).strip()
                    
                    # Count images in the folder
                    try:
                        image_count = len(list_image_files(root_path / folder_name))
                    except (PermissionError, FileNotFoundError):
                        image_count = 0
                    
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
                    
                    folder_entry: ExtractFolder = {
                        'name': folder_name,
                        'title': title,
                        'season': season,
                        'episode': episode,
                        'mtime': mtime,
                        'image_count': image_count,
                        'cover_filename': cover_filename,
                        'cover_url': cover_url,
                        'cover_thumb_url': cover_thumb_url,
                    }
                    entries.append(folder_entry)
        except PermissionError:
            pass
    
    # Sort by most recent first
    entries.sort(key=lambda x: (x['mtime'], x['name'].lower()), reverse=True)
    return entries, root_path
