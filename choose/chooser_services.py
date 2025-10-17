"""Choose app service functions for the chooser interface."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TypedDict

from common.utils import (
    extract_root,
    get_folder_path,
    list_image_files,
    parse_season_episode,
    thumbnail_url,
    validate_folder_name,
    wallpaper_url,
)
from .models import FolderProgress, ImageDecision


class FolderImage(TypedDict):
    """Metadata for an image in the chooser interface."""
    
    name: str
    url: str
    thumb_url: str | None
    decision: str


@dataclass(slots=True, frozen=True)
class FolderContext:
    """Context data for the chooser interface."""
    
    folder: str
    images: list[FolderImage]
    selected_index: int
    selected_image_url: str
    selected_image_name: str
    root: str
    path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


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
    root_path = extract_root()  # Use extract root for chooser
    target = get_folder_path(safe_name, root_path)

    try:
        files = list_image_files(target)
    except PermissionError:
        files = []
    
    # Filter files by season/episode if specified
    if season is not None or episode is not None:
        filtered_files = []
        for name in files:
            file_season, file_episode = parse_season_episode(name)
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
