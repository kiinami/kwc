from __future__ import annotations

import json
import logging
import os
import re
import shutil
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from django.utils.safestring import mark_safe

from extract.utils import render_pattern

from .models import FolderProgress, ImageDecision
from .utils import (
    add_version_suffix,
    discard_root,
    extraction_root,
    find_cover_filename,
    get_folder_path,
    list_image_files,
    parse_folder_name,
    parse_season_episode,
    parse_title_year_from_folder,
    parse_version_suffix,
    strip_version_suffix,
    thumbnail_url,
    validate_folder_name,
    wallpaper_url,
    wallpapers_root,
)

logger = logging.getLogger(__name__)


class GalleryImage(TypedDict):
    name: str
    url: str
    thumb_url: str | None
    version_suffix: str  # e.g., "U", "UM", "" for base
    base_name: str  # filename without version suffix
    versions: list[dict[str, str]]  # list of {name, url, thumb_url, version_suffix} for all versions
    versions_json: str  # JSON-encoded versions for template use


class GallerySection(TypedDict):
    """A group of images for the same season/episode combination."""
    title: str
    season: str
    episode: str
    images: list[GalleryImage]
    choose_url: str


class FolderImage(TypedDict):
    name: str
    url: str
    thumb_url: str | None
    decision: str


@dataclass(slots=True, frozen=True)
class GalleryContext:
    folder: str
    title: str
    year: str
    year_raw: int | None
    cover_url: str | None
    cover_thumb_url: str | None
    choose_url: str
    images: list[GalleryImage]  # kept for backward compatibility
    sections: list[GallerySection]  # new grouped view
    root: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class FolderContext:
    folder: str
    images: list[FolderImage]
    selected_index: int
    selected_image_url: str
    selected_image_name: str
    root: str
    path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def format_section_title(season: str, episode: str) -> str:
    """Format a human-readable section title from season/episode identifiers.
    
    Args:
        season: Season identifier (e.g., "01", "1", or "")
        episode: Episode identifier (e.g., "03", "IN", "OU", or "")
        
    Returns:
        Formatted title like "Season 1 Episode 3", "Season 1 Intro", "Season 1", or "General"
    """
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
        # Check for special episode markers
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


def list_gallery_images(folder: str, root: Path | None = None) -> GalleryContext:
    safe_name = validate_folder_name(folder)
    root_path = root or wallpapers_root()
    target = get_folder_path(safe_name, root_path)

    try:
        files = list_image_files(target)
    except PermissionError:
        files: list[str] = []  # type: ignore[no-redef]

    title, year_int = parse_folder_name(safe_name)
    year_display = str(year_int) if year_int is not None else ""

    cover_filename = find_cover_filename(target, files)
    cover_url = (
        wallpaper_url(safe_name, cover_filename, root=root_path)
        if cover_filename
        else None
    )
    cover_thumb_url = (
        thumbnail_url(safe_name, cover_filename, width=420, root=root_path)
        if cover_filename
        else None
    )

    # First, group files by their base name (without version suffix) to identify version sets
    version_groups: dict[str, list[str]] = defaultdict(list)
    for name in files:
        valid_suffix, invalid_suffix = parse_version_suffix(name)
        if valid_suffix or not invalid_suffix:
            # Valid suffix or no suffix - group by base name
            base_name = strip_version_suffix(name)
            version_groups[base_name].append(name)
        else:
            # Invalid suffix - treat as separate image
            version_groups[name].append(name)
    
    # Build gallery images with version information
    # For each version group, the base image (no suffix) should be the "primary" one
    processed_files: set[str] = set()
    images_with_versions: list[GalleryImage] = []
    
    # Maintain original file order by iterating through sorted files
    # and processing each version group only once (when we see its first member)
    for name in files:
        if name in processed_files:
            continue
            
        valid_suffix, invalid_suffix = parse_version_suffix(name)
        if valid_suffix or not invalid_suffix:
            # Valid suffix or no suffix - find its version group
            base_name = strip_version_suffix(name)
            version_files = version_groups[base_name]
        else:
            # Invalid suffix - treat as separate image
            version_files = version_groups[name]
        
        # Sort so base image (no suffix) comes first, then alphabetically by suffix
        def sort_key(filename: str) -> tuple[int, str]:
            suffix, _ = parse_version_suffix(filename)
            # Base image (no suffix) sorts first (0), others by suffix (1)
            return (0 if not suffix else 1, suffix)
        
        sorted_versions = sorted(version_files, key=sort_key)
        primary_name = sorted_versions[0]
        
        # Build version info for all files in this group
        versions = []
        for vname in sorted_versions:
            vsuffix, _ = parse_version_suffix(vname)
            versions.append({
                "name": vname,
                "url": wallpaper_url(safe_name, vname, root=root_path),
                "thumb_url": thumbnail_url(safe_name, vname, width=512, root=root_path),
                "version_suffix": vsuffix,
            })
        
        # Create the primary gallery image (represents the whole version stack)
        primary_suffix, _ = parse_version_suffix(primary_name)
        image: GalleryImage = {
            "name": primary_name,
            "url": wallpaper_url(safe_name, primary_name, root=root_path),
            "thumb_url": thumbnail_url(safe_name, primary_name, width=512, root=root_path),
            "version_suffix": primary_suffix,
            "base_name": strip_version_suffix(name) if (valid_suffix or not invalid_suffix) else name,
            "versions": versions,  # type: ignore[typeddict-item]
            "versions_json": mark_safe(json.dumps(versions)),  # JSON-encoded for template
        }
        images_with_versions.append(image)
        processed_files.update(version_files)

    # Build flat list of images (for backward compatibility - use primary images only)
    images: list[GalleryImage] = images_with_versions

    # Group images by season/episode
    grouped: dict[tuple[str, str], list[GalleryImage]] = defaultdict(list)
    for image in images_with_versions:
        # Parse season/episode from the base name (without suffix)
        base_name = image["base_name"]
        season, episode = parse_season_episode(base_name)
        key = (season, episode)
        grouped[key].append(image)
    
    # Convert grouped dict to sorted list of sections
    # Sort order: General, Season X (or episode-only), Season X Intro, Season X Episodes, Season X Outro
    def sort_key(item: tuple[tuple[str, str], list[GalleryImage]]) -> tuple:  # type: ignore[no-redef]
        season, episode = item[0]
        # Empty season/episode comes first (General section)
        if not season and not episode:
            return (0, 0, 0, "")
        
        # Parse season as int if possible
        # For episode-only patterns (no season), treat as season 1
        try:
            season_int = int(season) if season else 1
        except ValueError:
            season_int = 999999
        
        # Handle empty episode (season-only) - comes right after General
        if not episode:
            return (season_int, 1, 0, "")
        
        # Handle special episodes (IN, OU)
        episode_upper = episode.upper()
        if episode_upper == "IN":
            # Intro comes after season-only
            return (season_int, 2, 0, "")
        elif episode_upper == "OU":
            # Outro comes at the end after all episodes
            return (season_int, 999998, 0, "")
        
        # Parse episode as int if possible, otherwise use string sorting
        try:
            episode_int = int(episode)
            episode_str = ""
            # Regular episodes come after intro but before outro
            return (season_int, 3, episode_int, episode_str)
        except ValueError:
            episode_int = 999999
            episode_str = episode_upper
            return (season_int, 4, episode_int, episode_str)
    
    sorted_groups = sorted(grouped.items(), key=sort_key)  # type: ignore[arg-type]
    
    sections: list[GallerySection] = []
    for (season, episode), group_images in sorted_groups:
        # Build section-specific choose URL with query params for filtering
        # Always add query params to ensure proper filtering by section
        params = {
            'season': season,
            'episode': episode,
        }
        section_choose_url = reverse("choose:folder", kwargs={"folder": safe_name})
        section_choose_url = f"{section_choose_url}?{urlencode(params)}"
        
        sections.append({
            "title": format_section_title(season, episode),
            "season": season,
            "episode": episode,
            "images": group_images,
            "choose_url": section_choose_url,
        })

    choose_url = reverse("choose:folder", kwargs={"folder": safe_name})

    return GalleryContext(
        folder=safe_name,
        title=title,
        year=year_display,
        year_raw=year_int,
        cover_url=cover_url,
        cover_thumb_url=cover_thumb_url,
        choose_url=choose_url,
        images=images,
        sections=sections,
        root=str(root_path),
    )


def load_folder_context(
    folder: str,
    season: str | None = None,
    episode: str | None = None,
    root: Path | None = None,
) -> FolderContext:
    """Load folder context for the chooser UI.
    
    Args:
        folder: The folder name to load
        season: Optional season filter (e.g., "01")
        episode: Optional episode filter (e.g., "03", "IN", "OU")
        root: Optional root directory (defaults to wallpapers_root)
        
    Returns:
        FolderContext with images (optionally filtered by section)
    """
    safe_name = validate_folder_name(folder)
    root_path = root or wallpapers_root()
    target = get_folder_path(safe_name, root_path)

    try:
        files = list_image_files(target)
    except PermissionError:
        files = []
    
    # Filter files by season/episode if specified
    # Note: Empty strings mean we want to filter for the General section (no season/episode)
    if season is not None or episode is not None:
        filtered_files = []
        for name in files:
            file_season, file_episode = parse_season_episode(name)
            # Match if both season and episode match exactly (including empty strings)
            season_matches = season is None or file_season == season
            episode_matches = episode is None or file_episode == episode
            if season_matches and episode_matches:
                filtered_files.append(name)
        files = filtered_files

    decisions_qs = ImageDecision.objects.filter(folder=safe_name)
    decisions = list(decisions_qs.order_by("decided_at", "filename"))
    decision_map = {decision.filename: decision.decision for decision in decisions}

    images: list[FolderImage] = [
        {
            "name": name,
            "url": wallpaper_url(safe_name, name, root=root_path),
            "thumb_url": thumbnail_url(safe_name, name, width=320, root=root_path),
            "decision": decision_map.get(name, ""),
        }
        for name in files
    ]

    selected_index = -1
    progress = FolderProgress.objects.filter(folder=safe_name).first()
    start_index = 0
    if progress and images:
        anchor_idx = -1
        if progress.last_classified_name:
            for idx, image in enumerate(images):
                if image["name"] == progress.last_classified_name:
                    anchor_idx = idx
                    break
        if anchor_idx != -1:
            start_index = anchor_idx + 1
        elif progress.keep_count:
            start_index = progress.keep_count
    if images:
        if start_index >= len(images):
            start_index = len(images) - 1
        start_index = max(start_index, 0)
        for idx in range(start_index, len(images)):
            if not images[idx].get("decision"):
                selected_index = idx
                break
        if selected_index == -1:
            selected_index = start_index

    selected_image_url = (
        images[selected_index]["url"] if images and selected_index >= 0 else ""
    )
    selected_image_name = (
        images[selected_index]["name"] if images and selected_index >= 0 else ""
    )


    return FolderContext(
        folder=safe_name,
        images=images,
        selected_index=selected_index,
        selected_image_url=selected_image_url,
        selected_image_name=selected_image_name,
        root=str(root_path),
        path=str(target),
    )


def _get_max_counters(folder_path: Path) -> dict[tuple[str, str], int]:
    """Scan a folder and return max counter for each season/episode group."""
    counters: dict[tuple[str, str], int] = defaultdict(int)
    if not folder_path.exists():
        return counters
        
    try:
        files = list_image_files(folder_path)
    except PermissionError:
        return counters

    for fname in files:
        base_name = strip_version_suffix(fname)
        stem = os.path.splitext(base_name)[0]
        
        # Parse Season/Episode
        season, episode = parse_season_episode(stem)
        
        # Parse Counter
        counter_match = re.search(r"(\d+)$", stem)
        if counter_match:
            try:
                val = int(counter_match.group(1))
                key = (season, episode)
                counters[key] = max(counters[key], val)
            except ValueError:
                # Ignore malformed counter values and continue
                pass
    return counters


def ingest_inbox_folder(folder_name: str) -> dict[str, Any]:
    """Move decisions from Inbox to Library/Discard.
    
    Kept files: Moved to Library, appended to existing series.
    Discarded files: Moved to Discard folder.
    Undecided files: Remain in Inbox.
    
    If Inbox becomes empty, the folder is removed.
    """
    safe_name = validate_folder_name(folder_name)
    inbox_root = extraction_root()
    source_path = get_folder_path(safe_name, root=inbox_root)

    # Ensure destinations exist
    lib_path = wallpapers_root() / safe_name
    lib_path.mkdir(parents=True, exist_ok=True)
    
    trash_path = discard_root() / safe_name
    trash_path.mkdir(parents=True, exist_ok=True)

    # Load file list and decisions
    try:
        # Check permission early
        if not source_path.exists():
             return {"ok": False, "error": "folder_not_found"}
    except PermissionError as exc:
        raise OSError(f"Permission denied scanning {safe_name}") from exc

    decisions_qs = ImageDecision.objects.filter(folder=safe_name)
    
    # Prepare batch state
    base_title, parsed_year = parse_title_year_from_folder(safe_name)
    pattern = settings.EXTRACT_IMAGE_PATTERN
    
    # Load existing library counters to append correctly
    current_counters = _get_max_counters(lib_path)
    
    moved_keeps = 0
    moved_trash = 0
    errors: list[str] = []
    
    # Process files
    # We iterate valid decisions first for order, then check file existence
    
    # Sort keeps by decision time to respect user order
    sorted_keeps = decisions_qs.filter(decision=ImageDecision.DECISION_KEEP).order_by("decided_at", "filename")
    keep_filenames = [d.filename for d in sorted_keeps]
    
    # Process Keeps
    # We must group by base name to ensure versions get same counter? 
    # Current policy: Treat versions as separate files with suffixes.
    # But they should share the counter if they are versions of same image.
    # Map base_name -> assigned_counter to reuse it for versions.
    assigned_counters: dict[str, int] = {} # base_name_in_inbox -> assigned_counter
    
    for filename in keep_filenames:
        src = source_path / filename
        if not src.exists():
            continue
            
        # Parse info
        suffix, _ = parse_version_suffix(filename)
        base_name_inbox = strip_version_suffix(filename)
        stem = os.path.splitext(base_name_inbox)[0]
        original_ext = os.path.splitext(base_name_inbox)[1]
        
        season, episode = parse_season_episode(stem)
        key = (season, episode)
        
        # Determine counter
        if base_name_inbox in assigned_counters:
            count = assigned_counters[base_name_inbox]
        else:
            current_counters[key] += 1
            count = current_counters[key]
            assigned_counters[base_name_inbox] = count
            
        # render new name
        values: dict[str, object] = {
            "title": base_title,
            "base_title": base_title,
            "year": parsed_year or "",
            "season": int(season) if season and season.isdigit() else season,
            "episode": int(episode) if episode and episode.isdigit() else episode,
            "counter": count,
        }
        new_base_name = render_pattern(pattern, values)
        
        # Preserve original file extension by replacing pattern's extension
        pattern_stem = os.path.splitext(new_base_name)[0]
        new_base_name = pattern_stem + original_ext
        
        new_name = add_version_suffix(new_base_name, suffix)
        
        dest = lib_path / new_name
        
        # Prevent overwriting existing library files
        if dest.exists():
            # This shouldn't happen with monotonic counters, but race conditions/manual changes exists
            # Fallback: keep incrementing until free
            while dest.exists():
                current_counters[key] += 1
                count = current_counters[key]
                values["counter"] = count
                new_base_name = render_pattern(pattern, values)
                # Preserve original file extension
                pattern_stem = os.path.splitext(new_base_name)[0]
                new_base_name = pattern_stem + original_ext
                new_name = add_version_suffix(new_base_name, suffix)
                dest = lib_path / new_name
            # Update assigned map for subsequent versions
            assigned_counters[base_name_inbox] = count

        try:
            shutil.move(str(src), str(dest))
            moved_keeps += 1
            # Remove decision
            ImageDecision.objects.filter(folder=safe_name, filename=filename).delete()
        except OSError as exc:
            errors.append(f"Failed to move {filename} to library: {exc}")

    # Process Deletes (Trash)
    trash_decisions = decisions_qs.filter(decision=ImageDecision.DECISION_DELETE)
    for d in trash_decisions:
        filename = d.filename
        src = source_path / filename
        if not src.exists():
            continue
            
        dest = trash_path / filename
        
        # Handle existing files with the same name in trash folder
        if dest.exists():
            # Append timestamp to prevent collision
            stem = dest.stem
            suffix = dest.suffix
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = trash_path / f"{stem}_{timestamp}{suffix}"
        
        try:
            shutil.move(str(src), str(dest))
            moved_trash += 1
            ImageDecision.objects.filter(folder=safe_name, filename=filename).delete()
        except OSError as exc:
            errors.append(f"Failed to move {filename} to trash: {exc}")

    # Cleanup
    remaining_files = list_image_files(source_path)
    if not remaining_files:
        # If empty (ignoring hidden files), delete folder
        try:
            shutil.rmtree(source_path)
            shutil.rmtree(trash_path, ignore_errors=True) # Optional: clean empty trash folder? No, keep history.
        except OSError as exc:
            errors.append(f"Failed to remove empty inbox folder: {exc}")
            
    return {
        "ok": len(errors) == 0,
        "moved_library": moved_keeps,
        "moved_trash": moved_trash,
        "remaining": len(remaining_files),
        "errors": errors
    }
