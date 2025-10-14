from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import TypedDict

from django.urls import reverse

from .models import FolderProgress, ImageDecision
from .utils import (
    find_cover_filename,
    get_folder_path,
    list_image_files,
    parse_folder_name,
    parse_season_episode,
    thumbnail_url,
    validate_folder_name,
    wallpaper_url,
    wallpapers_root,
)


class GalleryImage(TypedDict):
    name: str
    url: str
    thumb_url: str | None


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


def list_gallery_images(folder: str) -> GalleryContext:
    safe_name = validate_folder_name(folder)
    root_path = wallpapers_root()
    target = get_folder_path(safe_name, root_path)

    try:
        files = list_image_files(target)
    except PermissionError:
        files: list[str] = []

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

    # Build flat list of images (for backward compatibility)
    images: list[GalleryImage] = [
        {
            "name": name,
            "url": wallpaper_url(safe_name, name, root=root_path),
            "thumb_url": thumbnail_url(safe_name, name, width=512, root=root_path),
        }
        for name in files
    ]

    # Group images by season/episode
    grouped: dict[tuple[str, str], list[GalleryImage]] = defaultdict(list)
    for name in files:
        season, episode = parse_season_episode(name)
        key = (season, episode)
        image: GalleryImage = {
            "name": name,
            "url": wallpaper_url(safe_name, name, root=root_path),
            "thumb_url": thumbnail_url(safe_name, name, width=512, root=root_path),
        }
        grouped[key].append(image)
    
    # Convert grouped dict to sorted list of sections
    # Sort by season (numeric), then episode (special like IN/OU before numeric)
    def sort_key(item: tuple[tuple[str, str], list[GalleryImage]]) -> tuple:
        season, episode = item[0]
        # Empty season/episode comes first (General section)
        if not season and not episode:
            return (0, 0, 0, "")
        
        # Parse season as int if possible
        try:
            season_int = int(season) if season else 999999
        except ValueError:
            season_int = 999999
        
        # Handle special episodes (IN, OU) - they should come before numeric episodes
        episode_upper = episode.upper() if episode else ""
        if episode_upper == "IN":
            # Intro comes first in the season
            return (season_int, 1, 0, "")
        elif episode_upper == "OU":
            # Outro comes at the end after all episodes
            return (season_int, 999998, 0, "")
        
        # Parse episode as int if possible, otherwise use string sorting
        try:
            episode_int = int(episode) if episode else 0
            episode_str = ""
            # Regular episodes come after intro but before outro
            return (season_int, 2, episode_int, episode_str)
        except ValueError:
            episode_int = 999999
            episode_str = episode.upper()
            return (season_int, 3, episode_int, episode_str)
    
    sorted_groups = sorted(grouped.items(), key=sort_key)
    
    sections: list[GallerySection] = []
    for (season, episode), group_images in sorted_groups:
        # Build section-specific choose URL with query params for filtering
        # Always add query params to ensure proper filtering by section
        from urllib.parse import urlencode
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


def load_folder_context(folder: str, season: str | None = None, episode: str | None = None) -> FolderContext:
    """Load folder context for the chooser UI.
    
    Args:
        folder: The folder name to load
        season: Optional season filter (e.g., "01")
        episode: Optional episode filter (e.g., "03", "IN", "OU")
        
    Returns:
        FolderContext with images (optionally filtered by section)
    """
    safe_name = validate_folder_name(folder)
    root_path = wallpapers_root()
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
        if start_index < 0:
            start_index = 0
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
