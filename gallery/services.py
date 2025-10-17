"""Gallery-specific service functions."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass

from django.urls import reverse

from common.models import GalleryImage, GallerySection
from common.utils import (
    find_cover_filename,
    format_section_title,
    get_folder_path,
    list_image_files,
    parse_folder_name,
    parse_season_episode,
    thumbnail_url,
    validate_folder_name,
    wallpaper_url,
    wallpapers_root,
)
from common.version_utils import parse_version_suffix, strip_version_suffix


@dataclass(slots=True, frozen=True)
class GalleryContext:
    """Context data for rendering a gallery view."""
    
    folder: str
    title: str
    year: str
    year_raw: int | None
    cover_url: str | None
    cover_thumb_url: str | None
    images: list[GalleryImage]
    sections: list[GallerySection]
    root: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def list_gallery_images(folder: str) -> GalleryContext:
    """Load and organize gallery images for a wallpapers folder.
    
    Args:
        folder: The folder name in the wallpapers directory
        
    Returns:
        GalleryContext with organized images and metadata
    """
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

    # Group files by their base name to identify version sets
    version_groups: dict[str, list[str]] = defaultdict(list)
    for name in files:
        base_name = strip_version_suffix(name)
        version_groups[base_name].append(name)

    # Create GalleryImage objects with version information
    images_by_season_episode: dict[tuple[str, str], list[GalleryImage]] = defaultdict(list)
    processed_bases = set()

    for name in files:
        base_name = strip_version_suffix(name)
        
        # Skip if we've already processed this base (will add versions later)
        if base_name in processed_bases:
            continue
        processed_bases.add(base_name)

        # Get all versions of this image
        versions_list = version_groups[base_name]
        
        # Parse season/episode from the base name
        season, episode = parse_season_episode(base_name)
        key = (season, episode)

        # Build version metadata for all versions
        version_metadata = []
        for ver_name in sorted(versions_list):
            ver_suffix, _ = parse_version_suffix(ver_name)
            version_metadata.append({
                'name': ver_name,
                'url': wallpaper_url(safe_name, ver_name, root=root_path),
                'thumb_url': thumbnail_url(safe_name, ver_name, width=400, root=root_path),
                'version_suffix': ver_suffix,
            })

        # The primary image is the base version (no suffix)
        primary_name = base_name
        if base_name not in versions_list:
            # Base doesn't exist, use first version as primary
            primary_name = versions_list[0]

        primary_suffix, _ = parse_version_suffix(primary_name)

        gallery_img: GalleryImage = {
            'name': primary_name,
            'url': wallpaper_url(safe_name, primary_name, root=root_path),
            'thumb_url': thumbnail_url(safe_name, primary_name, width=400, root=root_path),
            'version_suffix': primary_suffix,
            'base_name': base_name,
            'versions': version_metadata,
            'versions_json': json.dumps(version_metadata),
        }

        images_by_season_episode[key].append(gallery_img)

    # Build sections
    sections: list[GallerySection] = []
    all_images: list[GalleryImage] = []
    
    for key in sorted(images_by_season_episode.keys()):
        season, episode = key
        section_images = images_by_season_episode[key]
        section_title = format_section_title(season, episode)
        
        # Build choose URL for this section
        choose_url_kwargs = {'folder': safe_name}
        if season or episode:
            # Add query params for filtered section
            choose_url_base = reverse('choose:folder', kwargs=choose_url_kwargs)
            params = []
            if season:
                params.append(f"season={season}")
            if episode:
                params.append(f"episode={episode}")
            choose_url = f"{choose_url_base}?{'&'.join(params)}" if params else choose_url_base
        else:
            choose_url = reverse('choose:folder', kwargs=choose_url_kwargs)
        
        section: GallerySection = {
            'title': section_title,
            'season': season,
            'episode': episode,
            'images': section_images,
            'choose_url': choose_url,
        }
        sections.append(section)
        all_images.extend(section_images)

    return GalleryContext(
        folder=safe_name,
        title=title,
        year=year_display,
        year_raw=year_int,
        cover_url=cover_url,
        cover_thumb_url=cover_thumb_url,
        images=all_images,
        sections=sections,
        root=str(root_path),
    )
