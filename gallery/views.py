import os

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from choose.services import list_gallery_images
from choose.utils import (
    list_media_folders,
    parse_counter,
    parse_season_episode,
    validate_folder_name,
    wallpapers_root,
)


def index(request: HttpRequest) -> HttpResponse:
    """Gallery home page: list media folders with covers."""
    folders, root = list_media_folders()

    enriched: list[dict] = []
    for entry in folders:
        enriched.append(
            {
                **entry,
                'gallery_url': reverse('gallery:gallery', kwargs={'folder': entry['name']}),
            }
        )

    context = {
        'folders': enriched,
        'root': str(root),
    }
    return render(request, 'gallery/index.html', context)


def gallery(request: HttpRequest, folder: str) -> HttpResponse:
    """Grid gallery for a media folder with lightweight fullscreen viewer."""
    try:
        context = list_gallery_images(folder)
    except (ValueError, FileNotFoundError):
        raise Http404("Folder not found") from None

    return render(request, 'gallery/gallery.html', context.to_dict())


def lightbox(request: HttpRequest, folder: str, filename: str) -> HttpResponse:
    """Full-page lightbox viewer for a single image with sidebar showing metadata and versions."""
    try:
        context = list_gallery_images(folder)
    except (ValueError, FileNotFoundError):
        raise Http404("Folder not found") from None
    
    # Find the image in the gallery
    try:
        safe_name = validate_folder_name(folder)
    except ValueError:
        raise Http404("Invalid folder") from None
    
    safe_filename = os.path.basename(filename)
    if safe_filename != filename:
        raise Http404("Invalid filename")
    
    # Find the matching image in the gallery
    current_image = None
    current_index = -1
    for idx, img in enumerate(context.images):
        if img["name"] == safe_filename:
            current_image = img
            current_index = idx
            break
    
    if current_image is None:
        raise Http404("Image not found")
    
    # Get prev/next images
    prev_image = context.images[current_index - 1] if current_index > 0 else None
    next_image = context.images[current_index + 1] if current_index < len(context.images) - 1 else None
    
    # Get file info
    root = wallpapers_root()
    image_path = root / safe_name / safe_filename
    file_size = image_path.stat().st_size if image_path.exists() else 0
    file_ext = os.path.splitext(safe_filename)[1].lstrip('.')
    
    # Get image dimensions
    try:
        from PIL import Image  # noqa: PLC0415
        with Image.open(image_path) as img:
            width, height = img.size
    except Exception:
        width, height = 0, 0
    
    # Parse season/episode/counter metadata from filename
    season, episode = parse_season_episode(safe_filename)
    counter = parse_counter(safe_filename)

    def _normalize_number(token: str) -> str:
        if not token:
            return ""
        try:
            return str(int(token))
        except (ValueError, TypeError):
            return token

    season_display = _normalize_number(season) if season else ""
    if season and not season_display:
        season_display = season

    if episode:
        upper_episode = episode.upper()
        if upper_episode == "IN":
            episode_display = "Intro"
        elif upper_episode == "OU":
            episode_display = "Outro"
        else:
            normalized_episode = _normalize_number(episode)
            episode_display = normalized_episode or episode
    else:
        episode_display = ""
    
    lightbox_context = {
        **context.to_dict(),
        'current_image': current_image,
        'current_index': current_index,
        'prev_image': prev_image,
        'next_image': next_image,
        'file_size': file_size,
        'file_ext': file_ext.upper() if file_ext else '',
        'image_width': width,
        'image_height': height,
        'season': season,
        'season_display': season_display,
        'episode': episode,
        'episode_display': episode_display,
        'counter': counter,
        'filepath': str(image_path.relative_to(root)),
    }
    
    return render(request, 'gallery/lightbox.html', lightbox_context)

